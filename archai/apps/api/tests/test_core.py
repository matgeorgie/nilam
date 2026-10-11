import asyncio
import copy
import os
import tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
os.environ['LLM_PROVIDER']='mock'
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from app.schemas import HouseSpecification, RoomRequirement, Operation, Extraction, HouseShape
from app.layout import DeterministicLayoutEngine, validate, InfeasibleLayout
from app.services import demo_spec, apply_operation
from app.ai.providers import MockAIProvider, missing_fields
from app.main import app
from app.exports import model_export, drawing_export
from app.research.evaluation import diversity_report

engine=DeterministicLayoutEngine()

def test_seeded_demo_is_valid_and_connected():
    spec=demo_spec();layout=engine.generate(spec)
    assert not [c for c in layout.checks if c.status=='ERROR']
    assert len([r for r in layout.rooms if r.type=='bedroom'])==4
    assert sum(bool(r.attached_to) for r in layout.rooms)==3
    assert layout.score.adjacency_score==100
    parking_ids={r.id for r in layout.rooms if r.type=='parking'}
    assert parking_ids and all(any(d.kind=='vehicle' and d.room_a==room_id and d.room_b is None and d.width>=8 for d in layout.doors) for room_id in parking_ids)
    assert engine.generate(spec).rooms==layout.rooms

@pytest.mark.parametrize('width,length,floors,beds',[(30,40,1,2),(40,60,2,6),(25,45,2,3),(45,70,3,8),(10,15,1,1)])
def test_variable_layouts(width,length,floors,beds):
    spec=HouseSpecification(plot_width=width,plot_length=length,floors=floors,rooms=[RoomRequirement(type='bedroom',name='Bedroom',count=beds),RoomRequirement(type='kitchen',name='Kitchen'),RoomRequirement(type='living',name='Living')])
    if width<20:
        with pytest.raises(InfeasibleLayout):engine.generate(spec)
    else:
        layout=engine.generate(spec)
        assert not [c for c in validate(layout,spec) if c.status=='ERROR']

def test_impossible_does_not_generate():
    spec=HouseSpecification(plot_width=10,plot_length=10,floors=1,rooms=[RoomRequirement(type='bedroom',name='Bedroom',count=20)])
    with pytest.raises(InfeasibleLayout):engine.generate(spec)

def test_validation_detects_corruption():
    spec=demo_spec();original=engine.generate(spec)
    cases=[]
    layout=original.model_copy(deep=True);layout.rooms[3].polygon=layout.rooms[2].polygon;cases.append((layout,'No room overlaps'))
    layout=original.model_copy(deep=True);layout.rooms[2].polygon=[(x-50,y) for x,y in layout.rooms[2].polygon];cases.append((layout,'All rooms inside selected footprint'))
    layout=original.model_copy(deep=True);layout.doors[0].room_a='missing';cases.append((layout,'Doors connect valid spaces'))
    layout=original.model_copy(deep=True);layout.windows[0].position=-8;cases.append((layout,'Windows on exterior walls'))
    layout=original.model_copy(deep=True);layout.stairs=[];cases.append((layout,'Staircase connects floors'))
    layout=original.model_copy(deep=True);layout.rooms=[r for r in layout.rooms if r.type!='bedroom'];cases.append((layout,'4 bedrooms'))
    layout=original.model_copy(deep=True);layout.doors=[d for d in layout.doors if d.kind!='vehicle'];cases.append((layout,'Parking has road-reachable vehicle access'))
    for layout,name in cases:assert next(c for c in validate(layout,spec) if c.name==name).status=='ERROR'

def test_extraction_acceptance_and_clarification():
    provider=MockAIProvider()
    result=asyncio.run(provider.extract('I want a 2-floor house on a 30×50 ft plot with 4 bedrooms, 3 attached bathrooms, a common bathroom, kitchen, dining, living room, parking and staircase.',HouseSpecification()))
    s=result.specification
    assert (s.plot_width,s.plot_length,s.floors,s.parking_spaces)==(30,50,2,1)
    assert sum(r.count for r in s.rooms if r.type=='bedroom')==4
    assert sum(r.count for r in s.rooms if r.attached_bathroom)==3
    assert sum(r.count for r in s.rooms if r.type=='bathroom')==1
    assert not missing_fields(s)
    s=asyncio.run(provider.extract('Four bedrooms.',HouseSpecification())).specification
    assert set(missing_fields(s))=={'plot_width','plot_length','floors'}
    s=asyncio.run(provider.extract('30 by 50 feet, two floors.',s)).specification
    assert not missing_fields(s)

def test_success_criteria_metric_prompt_generates_ranked_vector_plan():
    text='2 bedroom single floor house, 2 bathrooms, open kitchen, dining, living room, one car porch, utility room, on a 12m × 20m plot with road on the south.'
    spec=asyncio.run(MockAIProvider().extract(text,HouseSpecification())).specification
    layout=engine.generate(spec);counts={kind:sum(r.type==kind for r in layout.rooms) for kind in ('bedroom','bathroom','kitchen','dining','living','utility','parking')}
    assert spec.unit=='meters' and spec.road_location=='south' and spec.preferences['open_kitchen'] is True
    assert counts=={'bedroom':2,'bathroom':2,'kitchen':1,'dining':1,'living':1,'utility':1,'parking':1}
    assert len(layout.alternatives)>=5
    assert all(r.polygon and len(r.polygon)>=4 for r in layout.rooms)
    assert not [c for c in layout.checks if c.status=='ERROR']

def test_strict_schema_rejects_malformed():
    with pytest.raises(ValidationError):Extraction.model_validate_json('{"specification":{"floors":-1},"explanation":"x"}')
    with pytest.raises(ValidationError):HouseSpecification.model_validate({'plot_width':float('nan')})
    with pytest.raises(ValidationError):HouseSpecification.model_validate({'plot_width':30,'coordinates':[1,2]})

def test_larger_master_changes_geometry():
    spec=demo_spec();before=engine.generate(spec)
    op=asyncio.run(MockAIProvider().modify('Make the master bedroom larger.',spec))
    assert op.operation=='resize_room'
    new_spec=apply_operation(spec,op,before);after=engine.generate(new_spec)
    area=lambda l:next(r.width*r.height for r in l.rooms if r.name=='Master bedroom')
    assert area(after)>area(before)
    assert not [c for c in after.checks if c.status=='ERROR']

@pytest.mark.parametrize('shape',[shape for shape in HouseShape if shape!=HouseShape.AUTO])
def test_each_selectable_footprint_generates_inside_boundary(shape):
    spec=demo_spec().model_copy(deep=True);spec.shape=shape
    layout=engine.generate(spec)
    assert layout.footprint and layout.footprint.shape==shape
    assert next(c for c in layout.checks if c.name=='All rooms inside selected footprint').status=='PASS'
    assert not [c for c in layout.checks if c.status=='ERROR']
    assert len({r.id for r in layout.rooms})==len(layout.rooms)

def test_auto_generation_retains_geometrically_distinct_candidates():
    spec=demo_spec().model_copy(deep=True);spec.shape=HouseShape.AUTO
    layout=engine.generate(spec)
    shapes={candidate.footprint.shape for candidate in layout.alternatives}
    assert len(layout.alternatives)>=3
    assert len(shapes)>=3
    assert layout.chosen_candidate_id
    assert all(not [c for c in candidate.checks if c.status=='ERROR'] for candidate in layout.alternatives)

def test_shape_diversity_across_100_generated_plans():
    shapes=[shape for shape in HouseShape if shape!=HouseShape.AUTO]
    layouts=[]
    for index in range(100):
        spec=HouseSpecification(plot_width=40+(index%3)*4,plot_length=56+(index%4)*4,shape=shapes[index%len(shapes)],floors=1,rooms=[RoomRequirement(type='bedroom',name='Bedroom',count=1+index%2),RoomRequirement(type='bathroom',name='Bathroom'),RoomRequirement(type='living',name='Living'),RoomRequirement(type='kitchen',name='Kitchen')])
        layouts.append(engine.generate(spec))
    report=diversity_report(layouts)
    assert report['total']==100
    assert report['passes']
    assert report['rectangle_ratio']<.95
    assert len(report['categories'])==7

def test_shape_change_is_a_revision_safe_operation():
    spec=demo_spec();before=engine.generate(spec)
    op=asyncio.run(MockAIProvider().modify('Change the house shape to L shape.',spec))
    assert op.operation=='set_house_shape' and op.shape==HouseShape.L_SHAPE
    changed=apply_operation(spec,op,before);after=engine.generate(changed)
    assert changed.shape==HouseShape.L_SHAPE
    assert after.footprint.shape==HouseShape.L_SHAPE
    assert after.footprint.boundary!=before.footprint.boundary

def test_exports_parse():
    import json
    from PIL import Image
    from io import BytesIO
    l=engine.generate(demo_spec())
    assert drawing_export(l,'svg')[0].startswith(b'<svg')
    assert drawing_export(l,'pdf')[0].startswith(b'%PDF')
    assert Image.open(BytesIO(drawing_export(l,'png')[0])).width>0
    assert model_export(l,'glb')[0][:4]==b'glTF'
    assert json.loads(model_export(l,'gltf')[0])['asset']['version']=='2.0'

def test_api_persistence_restore_and_local_access():
    with TestClient(app) as client:
        headers={}
        response=client.post('/api/projects/demo',headers=headers)
        assert response.status_code==200,response.text
        p=response.json();pid=p['id'];original=p['current_revision']
        assert client.get('/api/projects/'+pid,headers=headers).json()['layout']==p['layout']
        restored=client.post(f'/api/projects/{pid}/revisions/{original}/restore',headers=headers).json()
        assert restored['current_revision']!=original
        assert restored['layout']['rooms']==p['layout']['rooms']
        assert client.post(f'/api/projects/{pid}/undo',headers=headers).json()['current_revision']==original
        assert client.post(f'/api/projects/{pid}/redo',headers=headers).json()['current_revision']==restored['current_revision']
        assert len(client.get(f'/api/projects/{pid}/revisions',headers=headers).json())==2
        before=restored['current_revision']
        invalid_spec=demo_spec().model_dump();invalid_spec['plot_width']=10;invalid_spec['plot_length']=10
        bad=client.post(f'/api/projects/{pid}/requirements',json={'specification':invalid_spec},headers=headers)
        assert bad.status_code==422
        assert client.get(f'/api/projects/{pid}',headers=headers).json()['current_revision']==before
        assert client.get(f'/api/projects/{pid}/export/2d',headers=headers).status_code==200
        assert any(project['id']==pid for project in client.get('/api/projects').json())
        assert client.post('/api/auth/logout',headers=headers).status_code==404

def test_api_incremental_chat_and_project_creation():
    with TestClient(app) as client:
        h={}
        p=client.post('/api/projects',json={'name':'Test house'},headers=h).json()
        r=client.post(f"/api/projects/{p['id']}/chat",json={'message':'I need four bedrooms'},headers=h)
        assert r.status_code==200 and r.json()['reply']
        r=client.post(f"/api/projects/{p['id']}/requirements",json={'specification':demo_spec().model_dump()},headers=h)
        assert r.status_code==200,r.text
        assert r.json()['layout']

def test_api_candidate_selection_requires_a_retained_candidate():
    with TestClient(app) as client:
        headers={}
        project=client.post('/api/projects/demo',headers=headers).json();layout=project['layout']
        candidate=layout['alternatives'][-1] if layout['alternatives'] else None
        if candidate is None:
            assert client.post(f"/api/projects/{project['id']}/candidates/unknown/select",headers=headers).status_code==404
            return
        response=client.post(f"/api/projects/{project['id']}/candidates/{candidate['candidate_id']}/select",headers=headers)
        assert response.status_code==200,response.text
        selected=response.json()
        assert selected['current_revision']!=project['current_revision']
        assert selected['layout']['chosen_candidate_id']==candidate['candidate_id']
        assert selected['specification']['shape']==candidate['footprint']['shape']
