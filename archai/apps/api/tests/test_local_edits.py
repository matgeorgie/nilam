import pytest
from app.schemas import HouseSpecification,RoomRequirement,Operation
from app.simple_home import SimpleHomeLayoutEngine
from app.layout_edits import swap_rooms,requirement_operation
from app.services import apply_operation

def courtyard():
    spec=HouseSpecification(plot_width=50,plot_length=60,floors=1,shape='courtyard',road_location='north',parking_spaces=1,preferences={'open_kitchen':False},rooms=[RoomRequirement(type=k,name=k,count=3 if k=='bedroom' else 2 if k=='bathroom' else 1,preferred_floor=0) for k in ('bedroom','bathroom','living','dining','kitchen','utility')])
    return spec,SimpleHomeLayoutEngine().generate(spec)

def test_swap_keeps_other_geometry_and_original_revision():
    spec,layout=courtyard()
    a=next(r for r in layout.rooms if r.id=='bedroom-2');b=next(r for r in layout.rooms if r.type=='kitchen')
    changed=swap_rooms(layout,spec,Operation(operation='swap_rooms',target_room=a.id,parameters={'target':b.id}))
    assert changed.rooms!=layout.rooms
    assert next(r for r in layout.rooms if r.id==a.id).type=='bedroom'
    assert next(r for r in changed.rooms if r.id==a.id).type=='kitchen'
    assert all(r.model_dump()==next(v for v in changed.rooms if v.id==r.id).model_dump() for r in layout.rooms if r.id not in (a.id,b.id))
    assert changed.walls==layout.walls
    by_id={r.id:r for r in changed.rooms}
    assert any(b.id in (d.room_a,d.room_b) and (by_id[d.room_b].type=='hall' if d.room_a==b.id and d.room_b else by_id[d.room_a].type=='hall') for d in changed.doors)
    assert not [c for c in changed.checks if c.status=='ERROR']

def test_ambiguous_room_and_stair_swap_are_rejected():
    spec,layout=courtyard()
    with pytest.raises(ValueError):swap_rooms(layout,spec,Operation(operation='swap_rooms',target_room='bedroom',parameters={'target':'kitchen-1'}))
    with pytest.raises(ValueError):swap_rooms(layout,spec,Operation(operation='swap_rooms',target_room='hall-1',parameters={'target':'kitchen-1'}))

def test_remove_one_grouped_bedroom_keeps_other_requirements():
    spec,layout=courtyard()
    revised,op=requirement_operation(spec,layout,Operation(operation='remove_room',target_room='bedroom-2'))
    revised=apply_operation(revised,op,layout)
    assert sum(r.count for r in revised.rooms if r.type=='bedroom')==2
    assert sum(r.count for r in spec.rooms if r.type=='bedroom')==3
    assert sum(r.count for r in revised.rooms if r.type=='kitchen')==1
