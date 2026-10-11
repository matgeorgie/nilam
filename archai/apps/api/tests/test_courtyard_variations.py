import pytest
from shapely.geometry import Polygon
from app.schemas import HouseSpecification,RoomRequirement
from app.simple_home import SimpleHomeLayoutEngine
from app.layout import validate,physically_open_pairs

@pytest.mark.parametrize('road',['north','south','east','west'])
@pytest.mark.parametrize('beds',[2,3,4])
def test_courtyard_bedroom_edits_and_rotated_access(road,beds):
    w,l=(60,50) if road in ('east','west') else (50,60)
    spec=HouseSpecification(plot_width=w,plot_length=l,floors=1,shape='courtyard',road_location=road,parking_spaces=1,rooms=[RoomRequirement(type=k,name=k,count=beds if k=='bedroom' else 2 if k=='bathroom' else 1,preferred_floor=0) for k in ('bedroom','bathroom','living','dining','kitchen','utility')])
    layout=SimpleHomeLayoutEngine().generate(spec)
    assert layout.strategy=='SINGLE_COURTYARD'
    assert len([r for r in layout.rooms if r.type=='bedroom'])==beds
    assert not [c for c in validate(layout,spec) if c.status=='ERROR']
    court=Polygon(layout.footprint.courtyard)
    assert all(Polygon(r.polygon).intersection(court).area<1e-5 for r in layout.rooms)
    # Every bedroom has a door directly into circulation, not through another bedroom.
    by_id={r.id:r for r in layout.rooms}
    for bed in [r for r in layout.rooms if r.type=='bedroom']:
        assert any(bed.id in (d.room_a,d.room_b) and (by_id[d.room_b].type=='hall' if d.room_a==bed.id and d.room_b else by_id[d.room_a].type=='hall') for d in layout.doors)
