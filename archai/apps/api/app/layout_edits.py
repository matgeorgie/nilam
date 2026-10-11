from .schemas import HouseLayout,HouseSpecification,Operation
from .layout import validate,score,shared_wall,wall_line,add_door,physically_open_pairs

def exact_room(layout,reference):
    matches=[r for r in layout.rooms if r.id==reference or r.name.casefold()==(reference or '').casefold()]
    if len(matches)!=1:raise ValueError('Name one exact room to edit; the room reference is ambiguous or missing.')
    return matches[0]

def swap_rooms(layout:HouseLayout,spec:HouseSpecification,operation:Operation):
    """Swap the functions of two existing spaces; preserve all other geometry."""
    updated=layout.model_copy(deep=True)
    a=exact_room(updated,operation.target_room);b=exact_room(updated,str(operation.parameters.get('target','')))
    if a.id==b.id:raise ValueError('Choose two different rooms.')
    if a.floor!=b.floor:raise ValueError('Position swaps currently need two rooms on the same floor.')
    restricted={'hall','stair','parking','porch','veranda','balcony'}
    if a.type in restricted or b.type in restricted:raise ValueError('The entrance, stair, circulation and exterior spaces cannot be swapped with bedrooms or kitchens.')
    if a.attached_to or b.attached_to or any(r.attached_to in (a.id,b.id) for r in updated.rooms):raise ValueError('This swap would detach an ensuite. Change the bedroom and attached bathroom together using guided requirements.')
    # Room IDs refer to physical spaces. Openings remain attached to those spaces.
    for field in ('name','type','minimum_area','preferred_area','privacy_level'):
        av,bv=getattr(a,field),getattr(b,field);setattr(a,field,bv);setattr(b,field,av)
    for room in (a,b):
        if room.type!='bedroom':continue
        by_id={r.id:r for r in updated.rooms}
        if any(room.id in pair and any(by_id[rid].type not in ('bedroom','hall') for rid in pair if rid!=room.id) for pair in physically_open_pairs(updated)):
            raise ValueError('This space is open to a public room and cannot become a private bedroom through a simple swap. Enclose the kitchen first using the requirements editor.')
        halls=[r for r in updated.rooms if r.floor==room.floor and r.type=='hall' and shared_wall(updated,room,r)]
        existing=[d for d in updated.doors if room.id in (d.room_a,d.room_b) and any(h.id in (d.room_a,d.room_b) for h in halls)]
        if not existing:
            if not halls:raise ValueError('The new bedroom needs direct access from a common hall; this position swap cannot provide it.')
            hall=max(halls,key=lambda h:max(wall_line(w).length for w in shared_wall(updated,room,h)))
            wall=max(shared_wall(updated,room,hall),key=lambda w:wall_line(w).length)
            updated.doors=[d for d in updated.doors if room.id not in (d.room_a,d.room_b)]
            add_door(updated,room,hall,wall,3)
            # add_door numbers by length; removals can otherwise reuse an ID.
            updated.doors[-1].id='swap-entry-'+room.id
    updated.alternatives=[];updated.candidate_count=1;updated.chosen_candidate_id=None
    updated.checks=validate(updated,spec)
    errors=[c.detail for c in updated.checks if c.status=='ERROR']
    if errors:raise ValueError('The requested swap does not pass geometry/access checks: '+'; '.join(errors[:3]))
    updated.score=score(updated,spec)
    updated.generation_info={**updated.generation_info,'edit':'validated room-function swap','language_model':'Qwen 3.5 9B via LM Studio'}
    return updated

def requirement_operation(spec,layout,op):
    """Resolve model-selected geometry IDs to editable requirement instances."""
    op=op.model_copy(deep=True);spec=spec.model_copy(deep=True)
    if not op.target_room:return spec,op
    room=exact_room(layout,op.target_room)
    matches=[r for r in spec.rooms if r.name.casefold()==room.name.casefold()]
    if not matches:matches=[r for r in spec.rooms if r.type==room.type and r.preferred_floor in (None,room.floor)]
    if len(matches)!=1:raise ValueError('This room cannot be matched to a unique requirement. Review individual rooms in guided requirements.')
    requirement=matches[0]
    if requirement.count>1:
        requirement.count-=1
        instance=requirement.model_copy(deep=True);instance.count=1;instance.name=room.name;instance.preferred_floor=room.floor;spec.rooms.append(instance)
        requirement=instance
    op.target_room=requirement.name
    if op.operation in ('connect_rooms','disconnect_rooms'):
        op.parameters['target']=exact_room(layout,str(op.parameters.get('target',''))).name
    return spec,op
