import json
from ipaddress import ip_address
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field, ValidationError
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session
from .db import Base, engine, get_db, User, Project, Message, Revision, now
from .schemas import StrictModel, HouseSpecification, HouseLayout, HouseShape, Check
from .ai.providers import get_provider, missing_fields
from .ai.intent import compile_intent
from .intent_validation import evaluate_intent
from .layout import DeterministicLayoutEngine, validate
from .simple_home import SimpleHomeLayoutEngine
from .services import apply_operation, demo_spec
from .exports import drawing_export, model_export
from .cost_estimator import estimate_cost

def uid():return str(uuid4())

@asynccontextmanager
async def lifespan(app):
    if engine.dialect.name=='sqlite':Base.metadata.create_all(engine)
    yield

app=FastAPI(title='ArchAI API',version='1.0.0',lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,http://127.0.0.1:8000,http://127.0.0.1:5173').split(','),
    allow_methods=['*'],
    allow_headers=['*'],
    allow_private_network=True,
)

class ProjectInput(StrictModel):
    name: str = Field(default='Untitled home',min_length=1,max_length=100)
    specification: HouseSpecification = Field(default_factory=HouseSpecification)

class ChatInput(StrictModel):
    message: str = Field(min_length=1,max_length=5000)

class RequirementsInput(StrictModel):
    specification: HouseSpecification

class RenameInput(StrictModel):
    name: str = Field(min_length=1,max_length=100)

def current_user(request:Request,db:Session=Depends(get_db)):
    """One owner for this loopback-only design studio, with no account step."""
    host=request.client.host if request.client else ''
    try:
        local=ip_address(host).is_loopback
    except ValueError:
        local=host=='testclient'
    if not local:raise HTTPException(403,'The local design studio is available only on this device.')
    user=db.get(User,'local-workspace')
    if user is None:
        user=User(id='local-workspace',email='local@archai.invalid',name='Local designer',password_hash='disabled')
        db.add(user)
        db.flush()
        # Designs created by the previous local sign-in flow remain accessible.
        db.execute(update(Project).where(Project.user_id!='local-workspace').values(user_id='local-workspace'))
        db.commit()
    return user

@app.get('/api/health')
def health():return {'status':'ok','provider':get_provider().name,'database':engine.dialect.name,'access':'local','layout_profiles':['simple_home','courtyard_home']}

def own(db,user,project_id):
    project=db.get(Project,project_id)
    if not project or project.user_id!=user.id:raise HTTPException(404,'Project not found.')
    return project

def serialize(db,p,full=True):
    rev=db.get(Revision,p.current_revision) if p.current_revision else None
    result={'id':p.id,'name':p.name,'specification':p.specification,'updated_at':p.updated_at.isoformat(),'current_revision':p.current_revision,'can_undo':p.cursor>0,'can_redo':p.cursor<len(p.history)-1,'layout':rev.layout if rev else None}
    if full:
        result['messages']=[{'id':m.id,'role':m.role,'content':m.content} for m in db.scalars(select(Message).where(Message.project_id==p.id).order_by(Message.created_at))]
        result['provider']=get_provider().name
    return result

def full_checks(layout,spec):
    checks=validate(layout,spec)
    if layout.strategy=='LEGACY_FALLBACK':
        checks.append(Check(name='Simple-home layout unavailable',status='WARNING',detail='The legacy corridor-based generator was used; review circulation and room access.'))
    if spec.spatial_intent:
        compiled=compile_intent(spec,spec.spatial_intent)
        layout.checks=checks
        intent_checks,_=evaluate_intent(layout,compiled)
        checks.extend(intent_checks)
    return checks

def save_revision(db,p,spec,layout,title):
    checks=full_checks(layout,spec)
    if any(c.status=='ERROR' for c in checks):raise ValueError('The design failed hard-constraint validation and was not saved.')
    layout.checks=checks
    revision=Revision(id=uid(),project_id=p.id,title=title[:200],specification=spec.model_dump(),layout=layout.model_dump())
    db.add(revision);p.specification=spec.model_dump();p.current_revision=revision.id
    p.history=p.history[:p.cursor+1]+[revision.id];p.cursor=len(p.history)-1;p.updated_at=now();db.commit()

@lru_cache(maxsize=1)
def layout_model_adapter():
    from .ml.engine import MLGenerativeLayoutEngine
    return MLGenerativeLayoutEngine()

def generate_revision(db,p,spec,title):
    compiled=compile_intent(spec,spec.spatial_intent)
    evaluator=(lambda layout:evaluate_intent(layout,compiled)) if spec.spatial_intent else None
    
    layout = layout_model_adapter().generate(compiled.specification, evaluator)

    save_revision(db,p,compiled.specification,layout,title)
    return layout

class InterpretInput(StrictModel):
    message:str=Field(min_length=1,max_length=5000)
    specification:HouseSpecification

@app.post('/api/requirements/interpret')
async def interpret_requirements(body:InterpretInput,user:User=Depends(current_user)):
    from .ai.local_model import merge_brief
    try:
        decision=await get_provider().interpret(body.message,body.specification)
        if decision.mode!='requirements':return {'specification':body.specification.model_dump(),'questions':decision.questions or ['Please enter the room counts for each floor.'],'provider':get_provider().name}
        specification=merge_brief(body.specification,decision.requirements)
        return {'specification':specification.model_dump(),'questions':decision.questions,'provider':get_provider().name}
    except ValueError as exc:raise HTTPException(422,str(exc))
    except RuntimeError as exc:raise HTTPException(503,str(exc))

@app.post('/api/projects')
def create_project(body:ProjectInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=Project(id=uid(),user_id=user.id,name=body.name,specification=body.specification.model_dump(),history=[],cursor=-1)
    db.add(p);db.commit();return serialize(db,p)

@app.post('/api/projects/demo')
def create_demo(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=Project(id=uid(),user_id=user.id,name='Modern Family Villa',specification=demo_spec().model_dump(),history=[],cursor=-1)
    db.add(p);db.flush()
    try:generate_revision(db,p,demo_spec(),'Original concept')
    except ValueError as e:db.rollback();raise HTTPException(422,str(e))
    for role,content in [('user','I want a modern two-floor family house.'),('assistant','What are the plot dimensions?'),('user','30 by 50 feet.'),('assistant','How many bedrooms do you need?'),('user','Four bedrooms. The master bedroom should have an attached bathroom.'),('assistant','Do you want the remaining bedrooms to have attached bathrooms as well?'),('user','Two of them should. Add a common bathroom, kitchen, dining, living room, parking and two balconies.'),('assistant','Your concept is ready: four bedrooms, three attached bathrooms, and shared spaces across two floors. Select a room to explore it, or describe a change below.')]:db.add(Message(id=uid(),project_id=p.id,role=role,content=content))
    db.commit();return serialize(db,p)

@app.get('/api/projects')
def projects(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [serialize(db,p,False) for p in db.scalars(select(Project).where(Project.user_id==user.id).order_by(Project.updated_at.desc()))]

@app.get('/api/projects/{project_id}')
def get_project(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):return serialize(db,own(db,user,project_id))

@app.patch('/api/projects/{project_id}')
def rename(project_id:str,body:RenameInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id);p.name=body.name;p.updated_at=now();db.commit();return serialize(db,p)

@app.delete('/api/projects/{project_id}')
def remove(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    for entity in (Message,Revision):db.execute(delete(entity).where(entity.project_id==p.id))
    db.delete(p);db.commit();return {'ok':True}

@app.post('/api/projects/{project_id}/duplicate')
def duplicate(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    old=own(db,user,project_id);p=Project(id=uid(),user_id=user.id,name=old.name+' copy',specification=old.specification,history=[],cursor=-1);db.add(p);db.flush()
    rev=db.get(Revision,old.current_revision) if old.current_revision else None
    if rev:save_revision(db,p,HouseSpecification.model_validate(rev.specification),HouseLayout.model_validate(rev.layout),'Duplicated concept')
    db.commit();return serialize(db,p)

@app.post('/api/projects/{project_id}/requirements')
def requirements(project_id:str,body:RequirementsInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    try:
        if missing_fields(body.specification):raise ValueError('Provide plot dimensions, floors and rooms before saving requirements.')
        generate_revision(db,p,body.specification,'Updated requirements')
    except ValueError as e:raise HTTPException(422,str(e))
    return serialize(db,p)

@app.post('/api/projects/{project_id}/generate')
def generate(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    try:generate_revision(db,p,HouseSpecification.model_validate(p.specification),'Generated layout')
    except ValueError as e:raise HTTPException(422,str(e))
    return serialize(db,p)

@app.post('/api/projects/{project_id}/candidates/{candidate_id}/select')
def select_candidate(project_id:str,candidate_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    if not p.current_revision:raise HTTPException(404,'Generate candidate plans first.')
    rev=db.get(Revision,p.current_revision);current=HouseLayout.model_validate(rev.layout)
    candidate=next((item for item in current.alternatives if item.candidate_id==candidate_id),None)
    if not candidate:raise HTTPException(404,'Candidate is no longer available in this revision.')
    spec=HouseSpecification.model_validate(rev.specification).model_copy(deep=True)
    spec.shape=candidate.footprint.shape;spec.provenance['shape']='user'
    layout=HouseLayout(width=candidate.width,length=candidate.length,floors=candidate.floors,footprint=candidate.footprint,plot_boundary=current.plot_boundary,setback_boundary=current.setback_boundary,road_edge=current.road_edge,rooms=candidate.rooms,walls=candidate.walls,doors=candidate.doors,windows=candidate.windows,stairs=candidate.stairs,checks=candidate.checks,score=candidate.score,candidate_count=current.candidate_count,chosen_candidate_id=candidate.candidate_id,alternatives=current.alternatives)
    try:save_revision(db,p,spec,layout,'Selected candidate: '+candidate.label)
    except ValueError as e:raise HTTPException(422,str(e))
    return serialize(db,p)

@app.post('/api/projects/{project_id}/chat')
@app.post('/api/projects/{project_id}/modify')
async def chat(project_id:str,body:ChatInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id);spec=HouseSpecification.model_validate(p.specification);provider=get_provider();was_edit=bool(p.current_revision)
    try:
        from .ai.local_model import merge_brief
        from .layout_edits import swap_rooms,requirement_operation
        rev=db.get(Revision,p.current_revision) if p.current_revision else None
        current_layout=HouseLayout.model_validate(rev.layout) if rev else None
        recent=[{'role':m.role,'content':m.content} for m in db.scalars(select(Message).where(Message.project_id==p.id).order_by(Message.created_at.desc()).limit(4))]
        context_message=json.dumps({'recent_conversation':list(reversed(recent)),'latest_request':body.message}) if recent and current_layout else body.message
        decision=await provider.interpret(context_message,spec,current_layout)
        edited_layout=None
        if decision.mode=='clarify' or decision.questions:
            reply=' '.join(decision.questions) or 'Please identify the rooms you want to change.'
            for role,content in [('user',body.message),('assistant',reply)]:db.add(Message(id=uid(),project_id=p.id,role=role,content=content))
            db.commit();return {'project':serialize(db,p),'reply':reply,'missing_fields':[],'needs_clarification':True}
        if decision.mode=='requirements':
            spec=merge_brief(spec,decision.requirements)
        else:
            if not current_layout:raise ValueError('Create a plan using guided requirements before editing room positions.')
            # A swap preserves geometry; mixing regeneration and swaps is ambiguous.
            if any(op.operation=='swap_rooms' for op in decision.operations):
                if len(decision.operations)!=1:raise ValueError('Apply a position swap as a separate edit so the unchanged rooms can be preserved.')
                edited_layout=swap_rooms(current_layout,spec,decision.operations[0])
            else:
                for operation in decision.operations:
                    spec,operation=requirement_operation(spec,current_layout,operation)
                    spec=apply_operation(spec,operation,current_layout)
        if spec.spatial_intent:
            spec=compile_intent(spec,spec.spatial_intent).specification
        missing=missing_fields(spec)
        if missing:
            p.specification=spec.model_dump();reply='I have saved those requirements. Please provide '+', '.join(s.replace('_',' ') for s in missing)+'.'
        else:
            if edited_layout:
                save_revision(db,p,spec,edited_layout,body.message);layout=edited_layout
            else:layout=generate_revision(db,p,spec,body.message)
            warnings=sum(c.status=='WARNING' for c in layout.checks)
            reply=f'Your design is updated. All checked hard constraints pass across {layout.floors} floor(s).'+(f' There are {warnings} preferences to review in Validation.' if warnings else ' The 2D plan and 3D model are synchronized.')
            if was_edit and not edited_layout:
                reply+=' This edit regenerated the whole plan; other room positions may have changed.'
        for role,content in [('user',body.message),('assistant',reply)]:db.add(Message(id=uid(),project_id=p.id,role=role,content=content))
        db.commit();return {'project':serialize(db,p),'reply':reply,'missing_fields':missing}
    except (ValueError,ValidationError) as e:db.rollback();raise HTTPException(422,str(e))
    except RuntimeError as e:db.rollback();raise HTTPException(503,str(e))

@app.get('/api/projects/{project_id}/layout')
def get_layout(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    if not p.current_revision:raise HTTPException(404,'Generate a design first.')
    return db.get(Revision,p.current_revision).layout


@app.get('/api/projects/{project_id}/estimate')
def get_estimate(project_id:str,finish:str='standard',district:str|None=None,
                 user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    if not p.current_revision:raise HTTPException(404,'Generate a design first to see a budget.')
    revision=db.get(Revision,p.current_revision)
    try:
        return estimate_cost(HouseLayout.model_validate(revision.layout),
                             HouseSpecification.model_validate(revision.specification),
                             finish=finish,district=district)
    except ValueError as error:
        raise HTTPException(422,str(error)) from error

@app.post('/api/projects/{project_id}/validate')
def validation(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    if not p.current_revision:raise HTTPException(404,'Generate a design first.')
    rev=db.get(Revision,p.current_revision)
    return full_checks(HouseLayout.model_validate(rev.layout),HouseSpecification.model_validate(rev.specification))

@app.get('/api/projects/{project_id}/revisions')
def revisions(project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    own(db,user,project_id)
    return [{'id':r.id,'title':r.title,'created_at':r.created_at.isoformat(),'layout':r.layout,'specification':r.specification} for r in db.scalars(select(Revision).where(Revision.project_id==project_id).order_by(Revision.created_at.desc()))]

@app.post('/api/projects/{project_id}/revisions/{revision_id}/restore')
def restore(project_id:str,revision_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id);r=db.get(Revision,revision_id)
    if not r or r.project_id!=p.id:raise HTTPException(404,'Revision not found.')
    save_revision(db,p,HouseSpecification.model_validate(r.specification),HouseLayout.model_validate(r.layout),'Restored: '+r.title)
    return serialize(db,p)

@app.post('/api/projects/{project_id}/{action}')
def history_action(project_id:str,action:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    if action not in ('undo','redo'):raise HTTPException(404,'Unknown action.')
    cursor=p.cursor+(-1 if action=='undo' else 1)
    if not 0<=cursor<len(p.history):raise HTTPException(409,'No further history in this direction.')
    p.cursor=cursor;p.current_revision=p.history[cursor];p.specification=db.get(Revision,p.current_revision).specification;p.updated_at=now();db.commit();return serialize(db,p)

@app.get('/api/projects/{project_id}/export/{dimension}')
def export(project_id:str,dimension:str,format:str='svg',user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=own(db,user,project_id)
    if not p.current_revision:raise HTTPException(404,'Generate a design first.')
    rev=db.get(Revision,p.current_revision);layout=HouseLayout.model_validate(rev.layout)
    if any(c.status=='ERROR' for c in full_checks(layout,HouseSpecification.model_validate(rev.specification))):raise HTTPException(422,'This design has validation errors and cannot be exported.')
    try:
        if dimension=='2d':data,mime=drawing_export(layout,format)
        elif dimension=='3d':data,mime=model_export(layout,format)
        else:raise ValueError('Choose 2d or 3d.')
    except ValueError as e:raise HTTPException(422,str(e))
    return Response(data,media_type=mime,headers={'Content-Disposition':f'attachment; filename="archai-{p.id[:8]}.{format}"'})


class ReconstructionInput(StrictModel):
    image_base64: str = Field(max_length=11000000)
    image_width_feet: float = Field(gt=0,le=1000)

@app.post('/api/reconstruct-plan')
def reconstruct_plan(body:ReconstructionInput,user:User=Depends(current_user)):
    from .ml.reconstruction import reconstruct_image
    try:return {'layout':reconstruct_image(body.image_base64,body.image_width_feet).model_dump(),
                'notice':'Imported draft: inferred geometry and user-supplied image scale. Not a validated saved project.'}
    except (ValueError,RuntimeError,OSError) as exc:raise HTTPException(422,str(exc))

@app.post('/api/reconstruct-plan/export')
def export_reconstruction(body:HouseLayout,user:User=Depends(current_user)):
    if len(body.rooms)>100 or len(body.walls)>1000:raise HTTPException(422,'Plan too large.')
    data,mime=model_export(body,'glb')
    return Response(content=data,media_type=mime)


@app.post('/api/reconstruct-plan/geometry')
def import_geometry(body:HouseLayout,user:User=Depends(current_user)):
    from shapely.geometry import Polygon
    if not body.rooms or len(body.rooms)>100 or len(body.walls)>1000:raise HTTPException(422,'Invalid or oversized layout.')
    if body.width<=0 or body.length<=0 or not 1<=body.floors<=4:raise HTTPException(422,'Invalid plan dimensions.')
    if not all(Polygon(room.polygon).is_valid and Polygon(room.polygon).area>0 for room in body.rooms):raise HTTPException(422,'Invalid room polygon.')
    body.generation_info={**body.generation_info,'source':'imported layout JSON','draft':True}
    return {'layout':body.model_dump()}
