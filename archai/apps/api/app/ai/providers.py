import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import ValidationError
from ..schemas import Extraction, LLMExtraction, HouseSpecification, Operation, RoomRequirement, Relationship

PROMPTS = Path(__file__).parent / 'prompts'
WORDS = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'twenty':20,'a':1,'an':1}

def normalized(text: str) -> str:
    text = text.lower().replace('\u00d7','x').replace('×','x').replace('-',' ')
    return re.sub(r'\b('+'|'.join(WORDS)+r')\b', lambda m: str(WORDS[m[0]]), text)

def missing_fields(spec: HouseSpecification) -> list[str]:
    missing = [n for n in ('plot_width','plot_length','floors') if getattr(spec,n) is None]
    if not spec.rooms:
        missing.append('rooms')
    return missing

def is_full_design_brief(message: str) -> bool:
    """A full design request is not a single edit such as change plot width."""
    text=normalized(message)
    return bool(re.match(r'\s*(?:design|create|plan|i want|i need)\b',text)
                and re.search(r'\d+(?:\.\d+)?\s*(?:by|x)\s*\d',text)
                and re.search(r'(?:\d+|single)\s*(?:floor|storey|story)',text)
                and 'bedroom' in text and any(k in text for k in ('living','kitchen','dining')))


def floor_scoped_rooms(text: str):
    """Read explicit room lists on each floor; later design prose is not a room list."""
    headings=list(re.finditer(r'\b(ground|first|second|third)\s+floor\b|\b(upstairs|downstairs)\b',text))
    result=[]
    for index,heading in enumerate(headings):
        floor={'ground':0,'downstairs':0,'first':1,'upstairs':1,'second':2,'third':3}[heading[1] or heading[2]]
        section=text[heading.end():headings[index+1].start() if index+1<len(headings) else len(text)]
        section=re.split(r'(?<=[a-z])\.\s*|\bplace the staircase\b|\bkeep living\b',section,maxsplit=1)[0]
        for kind,pattern in [('bedroom',r'bedrooms?'),('bathroom',r'bathrooms?'),('balcony',r'balcon(?:y|ies)')]:
            for match in re.finditer(r'(\d+)\s+((?:(?:guest|shared|common|master|family|attached)\s+)*)'+pattern,section):
                adjective=match[2].strip()
                if kind=='bathroom' and adjective=='attached':
                    if any(r.type=='bedroom' and r.preferred_floor==floor and r.attached_bathroom for r in result):continue
                    raise ValueError('Please specify attached bathrooms using individual bedroom requirements; this demo parser cannot reliably assign them.')
                name=(adjective+' '+kind).strip().capitalize()
                attached_here=kind=='bedroom' and bool(re.match(r'\s+with\s+1\s+attached\s+bathroom',section[match.end():]))
                if attached_here and int(match[1])!=1:raise ValueError('Clarify which bedroom needs the attached bathroom.')
                result.append(RoomRequirement(type=kind,name=name,count=int(match[1]),preferred_floor=floor,attached_bathroom=attached_here))
        for kind,pattern in [('living',r'living room|family lounge'),('dining',r'dining(?: area| room)?'),('kitchen',r'kitchen'),('utility',r'utility')]:
            if re.search(r'\b(?:'+pattern+r')\b',section):
                result.append(RoomRequirement(type=kind,name='Family lounge' if kind=='living' and 'family lounge' in section else kind.capitalize(),preferred_floor=floor))
    return result

class AIProvider(ABC):
    name: str
    @abstractmethod
    async def extract(self, message: str, current: HouseSpecification) -> Extraction: ...
    @abstractmethod
    async def modify(self, message: str, current: HouseSpecification) -> Operation: ...

class MockAIProvider(AIProvider):
    """Explicit development-only rule parser, never described as an LLM."""
    name = 'Rule-based demo'
    async def extract(self, message, current):
        data = (HouseSpecification() if is_full_design_brief(message) else current).model_dump()
        text = normalized(message)
        dims = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres|ft|feet)?\s*(?:by|x)\s*(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres|ft|feet)?',text)
        if dims:
            data.update(plot_width=float(dims[1]),plot_length=float(dims[2]))
            data['provenance'].update(plot_width='user',plot_length='user')
        if re.search(r'(?:\d\s*m\b|\bmeters?\b|\bmetres?\b)',text): data['unit']='meters'
        elif re.search(r'(?:\d\s*ft\b|\bfeet\b)',text): data['unit']='feet'
        floor = re.search(r'(\d+)\s*(?:floors?|stor(?:ey|y)s?)',text)
        if floor:
            data['floors']=int(floor[1]); data['provenance']['floors']='user'
        if 'single floor' in text: data['floors']=1
        shape_match = re.search(r'\b(rectangle|l|u|t|c|stepped|irregular|courtyard|auto|best fit)\s*[-_ ]?shapes?\b|\b(rectangle|l_shape|u_shape|t_shape|c_shape|stepped|courtyard|auto)\b', text)
        if shape_match:
            raw = (shape_match.group(1) or shape_match.group(2)).replace('_shape','').replace('-shape','').replace(' shape','')
            raw={'irregular':'stepped','best fit':'auto'}.get(raw,raw)
            data['shape'] = raw if raw in ('rectangle','stepped','courtyard','auto') else f"{raw}_shape"
            data['provenance']['shape'] = 'user'
        road=re.search(r'road\s+(?:on|at|to)\s+(?:the\s+)?(north|south|east|west)',text)
        if road: data['road_location']=road[1];data['provenance']['road_location']='user'
        if 'open kitchen' in text: data['preferences']['open_kitchen']=True
        rooms = [RoomRequirement.model_validate(r) for r in data['rooms']]
        bed = re.search(r'(\d+)\s*bedrooms?',text)
        attached = re.search(r'(\d+)\s*(?:of them (?:should|have)|attached bathrooms?)',text)
        attached_count = int(attached[1]) if attached else (1 if 'master bedroom' in text and 'attached bathroom' in text else None)
        if bed or attached_count is not None:
            count = int(bed[1]) if bed else sum(r.count for r in rooms if r.type=='bedroom')
            if not count: count=1
            old_attached=sum(r.count for r in rooms if r.type=='bedroom' and r.attached_bathroom)
            ac = attached_count if attached_count is not None else min(old_attached,count)
            if 'of them' in text: ac=min(count,old_attached+(attached_count or 0))
            if ac>count: raise ValueError('Attached bathrooms exceed the bedroom count. Please clarify which rooms need them.')
            rooms=[r for r in rooms if r.type!='bedroom']
            for i in range(count): rooms.append(RoomRequirement(type='bedroom',name='Master bedroom' if i==0 else f'Bedroom {i+1}',attached_bathroom=i<ac))
        common=re.search(r'(\d+)\s*(?:common|shared) bathrooms?',text)
        bathroom=re.search(r'(\d+)\s*bathrooms?',text)
        if common or (bathroom and 'attached' not in text):
            rooms=[r for r in rooms if r.type!='bathroom']
            rooms.append(RoomRequirement(type='bathroom',name='Common bathroom',count=int((common or bathroom)[1])))
        for kind,pattern in [('kitchen',r'kitchen'),('dining',r'dining'),('living',r'living room'),('balcony',r'balcon(?:y|ies)'),('office',r'(?:office|work area)'),('utility',r'utility'),('veranda',r'veranda')]:
            if re.search(pattern,text):
                number=re.search(r'(\d+)\s*'+pattern,text)
                rooms=[r for r in rooms if r.type!=kind]
                rooms.append(RoomRequirement(type=kind,name=kind.capitalize() if kind!='living' else 'Living room',count=int(number[1]) if number else 1,preferred_floor=1 if kind=='balcony' and (data['floors'] or 1)>1 else None))
        scoped=floor_scoped_rooms(text)
        if scoped:
            replaced={r.type for r in scoped}
            rooms=[r for r in rooms if r.type not in replaced]+scoped
        if 'parking' in text or 'car porch' in text:
            number=re.search(r'(?:parking for\s*)?(\d+)\s*car',text)
            data['parking_spaces']=int(number[1]) if number else 1
        if any(word in text for word in ('accessible','accessibility','wheelchair')): data['preferences']['accessibility']=True
        if 'modern' in text: data['style']='Modern';data['provenance']['style']='user'
        if 'kitchen' in text and 'dining' in text and any(w in text for w in ('connected','next to','adjacent')):
            data['relationships']=[Relationship(source='kitchen',target='dining',relation='connected').model_dump()]
        data['rooms']=[r.model_dump() for r in rooms]
        data['provenance']['rooms']='user'
        data['provenance'].setdefault('minimum_room_areas','system_default')
        data['provenance'].setdefault('orientation','system_default')
        return Extraction(specification=HouseSpecification.model_validate(data), explanation='Requirements parsed using the rule-based development provider.')

    async def modify(self,message,current):
        text=normalized(message)
        target=next((r.name for r in current.rooms if r.name.lower() in text),None)
        if target is None:
            target=next((r.name for r in current.rooms if r.type in text),None)
        dims=re.search(r'(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres|ft|feet)?\s*(?:by|x)\s*(\d+(?:\.\d+)?)\s*(?:m|meter|meters|metre|metres|ft|feet)?',text)
        if 'plot' in text and dims: return Operation(operation='change_plot',parameters={'width':float(dims[1]),'length':float(dims[2])})
        floors=re.search(r'(\d+)\s*floors?',text)
        if floors: return Operation(operation='change_floor',parameters={'floors':int(floors[1])})
        shape_match = re.search(r'\b(rectangle|l|u|t|c|stepped|irregular|courtyard|auto|best fit)\s*[-_ ]?shapes?\b|\b(rectangle|l_shape|u_shape|t_shape|c_shape|stepped|courtyard|auto)\b', text)
        if shape_match:
            raw = (shape_match.group(1) or shape_match.group(2)).replace('_shape','').replace('-shape','').replace(' shape','')
            raw={'irregular':'stepped','best fit':'auto'}.get(raw,raw)
            target_shape = raw if raw in ('rectangle','stepped','courtyard','auto') else f"{raw}_shape"
            return Operation(operation='set_house_shape', shape=target_shape)
        if 'larger' in text or 'bigger' in text or 'smaller' in text or (dims and target):
            return Operation(operation='resize_room',target_room=target,parameters={'width':float(dims[1]),'length':float(dims[2])} if dims else {'factor':0.85 if 'smaller' in text else 1.2})
        if 'next to' in text or 'connected to' in text:
            types=[r.type for r in current.rooms if r.type in text]
            if len(set(types))>=2: return Operation(operation='connect_rooms',target_room=types[0],parameters={'target':list(dict.fromkeys(types))[1]})
        if 'remove' in text or 'delete' in text: return Operation(operation='remove_room',target_room=target)
        if 'add' in text:
            kind=next((k for k in ('bedroom','bathroom','balcony','office','kitchen','dining','living','utility') if k in text),None)
            if kind:
                params={'type':kind,'name':f'{kind.capitalize()}'}
                if 'first floor' in text: params['floor']=1
                return Operation(operation='add_room',parameters=params)
        if 'regenerate' in text: return Operation(operation='regenerate_layout')
        if 'style' in text: return Operation(operation='change_style',parameters={'style':message})
        raise ValueError('The demo parser supports adding/removing rooms, resizing, connecting rooms, changing floors or plot dimensions. Configure an LLM for broader language understanding.')

def get_provider() -> AIProvider:
    from .local_model import LocalModelProvider
    return LocalModelProvider()
