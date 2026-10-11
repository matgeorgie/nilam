from pathlib import Path
import pytest
from app.schemas import HouseSpecification, HouseShape, RoomRequirement
from app.simple_home import SimpleHomeLayoutEngine
from app.layout import validate, bounds
from app.stair_geometry import landing_zone, entry_edge

@pytest.mark.parametrize('parking',[0,1])
@pytest.mark.parametrize('floors',[2,3])
def test_guided_brief_reserves_stair_before_room_packing(parking,floors):
    spec=HouseSpecification.model_validate_json((Path(__file__).parent/'fixtures/guided-duplex-stair.json').read_text(encoding='utf-8'))
    spec.shape=HouseShape.RECTANGLE
    spec.parking_spaces=parking
    spec.floors=floors
    layout=SimpleHomeLayoutEngine().generate(spec)
    assert not [c.name for c in validate(layout,spec) if c.status=='ERROR']
    assert len(layout.stairs)==floors-1
    for stair in layout.stairs:
        assert stair.kind=='dogleg'
        zone=next(r for r in layout.rooms if r.id==f'stair-{stair.from_floor}')
        assert all(bounds(r).intersection(bounds(zone)).area<1e-6 for r in layout.rooms if r.floor==zone.floor and r.type!='stair')
        for f in (stair.from_floor,stair.to_floor):
            assert any(r.type=='hall' and r.floor==f and bounds(r).covers(landing_zone(stair)) for r in layout.rooms)

def test_suggested_duplex_description_has_family_lounge_and_ensuite():
    spec=HouseSpecification(plot_width=50,plot_length=60,floors=2,parking_spaces=1,rooms=[
        RoomRequirement(type=k,name=k,preferred_floor=0) for k in ('living','dining','kitchen','utility','bedroom','bathroom','porch')
    ]+[
        RoomRequirement(type='bedroom',name='Master bedroom',preferred_floor=1,attached_bathroom=True),
        RoomRequirement(type='bedroom',name='Second bedroom',preferred_floor=1),
        RoomRequirement(type='living',name='Family lounge',preferred_floor=1),
        RoomRequirement(type='bathroom',name='Upper shared bath',preferred_floor=1),
        RoomRequirement(type='balcony',name='Balcony',preferred_floor=1),
    ])
    spec.shape=HouseShape.RECTANGLE
    layout=SimpleHomeLayoutEngine().generate(spec)
    assert not [c.name for c in validate(layout,spec) if c.status=='ERROR']
    assert any(r.name=='Family lounge' and r.floor==1 for r in layout.rooms)
    master=next(r for r in layout.rooms if r.name=='Master bedroom')
    assert any(r.attached_to==master.id for r in layout.rooms)
