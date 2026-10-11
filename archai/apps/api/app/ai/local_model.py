"""In-process GGUF inference. No HTTP inference service or parser fallback."""
import asyncio,json,os,threading,time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field,model_validator
from ..schemas import StrictModel,HouseSpecification,Operation,HouseShape

MODEL_PATH=Path(__file__).parents[1]/'ml/language/qwen2.5-1.5b-instruct-q4_k_m.gguf'
LOCK=threading.Lock()
@contextmanager
def inference_lock():
    if not LOCK.acquire(blocking=False):raise RuntimeError('Local AI is processing another request. Use guided requirements or wait and try again.')
    try:yield
    finally:LOCK.release()

def deadline(seconds=90):
    from llama_cpp import StoppingCriteriaList
    start=time.monotonic()
    return StoppingCriteriaList([lambda ids,logits:time.monotonic()-start>seconds])

class ModelRoom(StrictModel):
    type:Literal['bedroom','bathroom','kitchen','dining','living','balcony','office','utility','porch','veranda']
    name:str
    count:int=Field(ge=1,le=8)
    preferred_floor:int=Field(ge=0,le=3)
    attached_bathroom:bool
    @model_validator(mode='after')
    def ensuite_owner(self):
        if self.attached_bathroom and self.type!='bedroom':raise ValueError('Only a bedroom can own an attached bathroom. Shared bathrooms must have attached_bathroom=false.')
        return self

class SiteDecision(StrictModel):
    plot_width:float|None
    plot_length:float|None
    floors:int|None
    unit:Literal['feet','meters']|None
    shape:HouseShape|None
    road_location:Literal['north','south','east','west']|None
    parking_spaces:int|None

class FloorDecision(StrictModel):
    rooms:list[ModelRoom]
    questions:list[str]

class BriefPatch(StrictModel):
    plot_width:float|None
    plot_length:float|None
    floors:int|None
    unit:Literal['feet','meters']
    shape:HouseShape
    road_location:Literal['north','south','east','west']
    parking_spaces:int
    # A complete room list, one bedroom per instance; bathrooms here are shared only.
    rooms:list[ModelRoom]|None=None

class Decision(StrictModel):
    mode:Literal['requirements','edit','clarify']
    questions:list[str]=Field(default_factory=list,max_length=5)
    requirements:BriefPatch|None=None
    operations:list[Operation]=Field(default_factory=list,max_length=6)

EDIT_SYSTEM="""Interpret ONLY the latest user request for an existing house. Earlier conversation provides context; never repeat earlier edits. Return JSON with mode=edit or clarify, requirements=null.
Use exact IDs from existing_rooms. Never guess between multiple bedrooms: ask which bedroom using mode=clarify, questions=[your question], operations=[].
Supported operations:
swap_rooms: target_room=ID of first room, parameters={target: ID of second room}; use for exchanging positions, e.g. kitchen where bedroom is and bedroom where kitchen is.
add_room: target_room=null (a new room has no existing ID), parameters={type,name,count,floor,attached_bathroom}; room types bedroom,bathroom,kitchen,dining,living,utility,office,balcony.
remove_room: target_room=exact ID.
resize_room: target_room=ID, parameters={width,length} or {factor:1.2}.
move_room: target_room=ID, parameters={floor:0-based number}. Moving to another side without a target room requires clarification.
connect_rooms: target_room=ID, parameters={target: other room ID}.
change_floor: parameters={floors:number}; change_plot: parameters={width,length}; set_house_shape: shape=rectangle/l_shape/u_shape/t_shape/c_shape/stepped/courtyard/auto.
regenerate_layout: no parameters. Do not invent other operations or coordinates. Questions=[] for unambiguous requests. Preserve all unspecified rooms.
Example output for swapping bedroom-1 with kitchen-1: {"mode":"edit","questions":[],"requirements":null,"operations":[{"operation":"swap_rooms","target_room":"bedroom-1","parameters":{"target":"kitchen-1"}}]}."""

@lru_cache(maxsize=1)
def model():
    path=Path(os.getenv('ARCHAI_MODEL_PATH',str(MODEL_PATH)))
    if not path.is_file():raise RuntimeError('Local language model is missing. Run scripts/Install-LocalAI.ps1. No rule parser was used.')
    try:
        from llama_cpp import Llama
        class TimedLlama(Llama):
            def create_completion(self,*args,**kwargs):
                kwargs['stopping_criteria']=deadline()
                return super().create_completion(*args,**kwargs)
        return TimedLlama(model_path=str(path),n_ctx=4096,n_batch=128,n_threads=4,n_gpu_layers=0,chat_format='chatml',verbose=False)
    except (ImportError,OSError) as exc:raise RuntimeError('Local AI runtime could not load. Run scripts/Install-LocalAI.ps1.') from exc

class LocalModelProvider:
    name='Qwen2.5 1.5B · local GGUF'
    async def interpret(self,message,current,layout=None):
        return await asyncio.to_thread(self._interpret,message,current,layout)
    def _interpret(self,message,current,layout):
        if layout is None:return self._requirements(message,current)
        brief={key:value for key,value in current.model_dump().items() if key in ('plot_width','plot_length','floors','unit','shape','road_location','parking_spaces','rooms')}
        # Remove irrelevant null/default room fields to keep the context small on 8 GB machines.
        brief['rooms']=[{k:v for k,v in r.items() if v is not None and k in ('type','name','count','preferred_floor','attached_bathroom')} for r in brief['rooms']]
        latest=message;conversation=[]
        try:
            previous=json.loads(message)
            if isinstance(previous,dict) and 'latest_request' in previous:
                latest=previous['latest_request'];conversation=previous.get('recent_conversation',[])[-4:]
        except ValueError:pass
        context={'site_and_requirements':brief,'existing_rooms':[{ 'id':r.id,'name':r.name,'type':r.type,'floor':r.floor,'attached_to':r.attached_to} for r in layout.rooms] if layout else [],'message':latest}
        messages=[{'role':'system','content':EDIT_SYSTEM},{'role':'user','content':json.dumps(context)},*conversation,{'role':'user','content':latest}]
        with inference_lock():
            llm=model()
            for attempt in range(2):
                self.last_output=None
                result=llm.create_chat_completion(messages=messages,temperature=0,max_tokens=450,response_format={'type':'json_object','schema':Decision.model_json_schema()})
                choice=result['choices'][0];self.last_output=choice['message']['content']
                if choice['finish_reason']!='stop':raise ValueError('The local model could not finish reading this description. Use the per-floor questions to review the requirements.')
                try:
                    decision=Decision.model_validate_json(choice['message']['content'])
                    if decision.mode=='requirements' and (decision.requirements is None or not decision.requirements.rooms):raise ValueError('No room requirements extracted.')
                    if decision.mode=='edit' and not decision.operations:raise ValueError('No edit specified.')
                    if layout and decision.mode=='edit':
                        # Validate model-selected identifiers against the user's references.
                        # This does not parse intent: it prevents a model from choosing an
                        # arbitrary instance when several rooms have the same function.
                        latest=message
                        try:latest=json.loads(message).get('latest_request',message)
                        except (ValueError,AttributeError):pass
                        for op in decision.operations:
                            if op.operation in ('add_room','add_balcony','set_house_shape','change_shape_parameters','change_plot','change_floor','change_style','regenerate_layout'):
                                op.target_room=None
                                continue
                            references=[op.target_room]
                            if op.operation in ('swap_rooms','connect_rooms','disconnect_rooms'):references.append(str(op.parameters.get('target','')))
                            for reference in filter(None,references):
                                chosen=[r for r in layout.rooms if r.id==reference or r.name.casefold()==reference.casefold()]
                                if len(chosen)!=1:return Decision(mode='clarify',questions=['Name the exact room you want to change.'])
                                room=chosen[0];peers=[r for r in layout.rooms if r.type==room.type and r.attached_to is None]
                                if len(peers)>1 and room.name.casefold() not in latest.casefold() and room.id.casefold() not in latest.casefold():
                                    return Decision(mode='clarify',questions=['Which '+room.type+' do you mean? Choose '+', '.join(r.name for r in peers)+'.'])
                    return decision
                except ValueError as exc:
                    if attempt:raise ValueError('The model could not reliably read the request. Use guided requirements, or name the exact rooms for the edit.') from exc
                    messages.append({'role':'assistant','content':choice['message']['content']})
                    messages.append({'role':'user','content':'Correct the JSON: '+str(exc)[:500]})

    def _complete(self,llm,messages,schema,output_model,max_tokens=650,attempts=2):
        for attempt in range(attempts):
            response=llm.create_chat_completion(messages=messages,temperature=0,max_tokens=max_tokens,response_format={'type':'json_object','schema':schema})
            choice=response['choices'][0];self.last_output=choice['message']['content']
            if choice['finish_reason']!='stop':raise ValueError('This description is too long for reliable local extraction. Enter the counts in guided requirements.')
            try:return output_model.model_validate_json(self.last_output)
            except ValueError as exc:
                if attempt==attempts-1:raise ValueError('The local model could not read this reliably. Use the per-floor questions to review the rooms.') from exc
                messages.extend([{'role':'assistant','content':self.last_output},{'role':'user','content':'Correct the JSON validation error: '+str(exc)[:700]}])

    def _requirements(self,message,current):
        # Site values are supplied by the form; the model reads one floor at a time.
        site_keys=('plot_width','plot_length','floors','unit','shape','road_location','parking_spaces')
        current_site={k:current.model_dump()[k] for k in site_keys}
        room_prompt='''Extract rooms for ONLY the requested floor from the user's description. Return JSON with rooms and questions.
Include every room requested ON THIS FLOOR. Ignore rooms explicitly assigned to other floors. Unscoped rooms belong to ground floor only. Ground floor=0, first floor=1, second floor=2.
Each room uses type,name,count,preferred_floor,attached_bathroom. Bedrooms without ensuites may be grouped with count equal to the requested number. Represent each bedroom with an ensuite separately so its owner is unambiguous. Use unique descriptive names. Types are bedroom,bathroom,kitchen,dining,living,balcony,office,utility,porch,veranda. Family lounge=living. Parking is not a room.
Set attached_bathroom=true ONLY for the specific bedroom explicitly described as having an ensuite or attached bathroom ON THIS FLOOR. Do not transfer a master bedroom's attached bathroom to a guest bedroom or another floor. All other bedrooms and all shared bathrooms use attached_bathroom=false. An ensuite is not a separate room. One shared bathroom is a separate bathroom record, count=1. Include all living, dining and kitchen rooms mentioned on this floor.
A front sit-out is ONE porch record. Do not also add a veranda for the same sit-out. Do not invent unrequested rooms. No requested rooms on this floor means rooms=[]. questions=[] unless the requirements are ambiguous. Do not add a staircase or hallway; those are generated later.
Return the JSON shape {"rooms":[{"type":"bedroom","name":"Bedroom","count":1,"preferred_floor":0,"attached_bathroom":false}],"questions":[]}, replacing the sample with ONLY the actual requested rooms for the selected floor.
'''
        with inference_lock():
            llm=model()
            # Site dimensions, floors, shape and road are explicit form inputs.
            # A small language model must not overwrite those authoritative values.
            site=SiteDecision.model_validate(current_site)
            if site.floors is None:return Decision(mode='clarify',questions=['How many floors should the house have?'])
            if not 1<=site.floors<=4:raise ValueError('Choose between one and four floors.')
            rooms=[];questions=[]
            for floor in range(site.floors):
                schema=FloorDecision.model_json_schema()
                schema['$defs']['ModelRoom']['properties']['preferred_floor']={'type':'integer','const':floor}
                try:
                    result=self._complete(llm,[{'role':'system','content':room_prompt+'\nExtract ONLY '+(['GROUND FLOOR','FIRST FLOOR','SECOND FLOOR','THIRD FLOOR'][floor])+' (index '+str(floor)+'). Do not include rooms assigned to any other floor.'},{'role':'user','content':message}],schema,FloorDecision,attempts=1)
                except ValueError:
                    return Decision(mode='requirements',requirements=BriefPatch(**site.model_dump(),rooms=rooms),questions=[f'I could not reliably read floor {floor}. Enter its bedrooms, kitchens, shared bathrooms and attached bathrooms using the questions below. Review every floor before generating.'])
                rooms.extend(result.rooms);questions.extend(result.questions)
            names=set()
            for room in rooms:
                if room.name.casefold() in names:room.name+=f' floor {room.preferred_floor}'
                names.add(room.name.casefold())
            return Decision(mode='requirements',requirements=BriefPatch(**site.model_dump(),rooms=rooms),questions=questions)

def merge_brief(current,patch):
    updates=patch.model_dump(exclude_none=True)
    data=current.model_dump();data.update(updates);data['spatial_intent']=None
    data['provenance'].update({key:'user' for key in updates})
    return HouseSpecification.model_validate(data)
