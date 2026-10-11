import pytest
from shapely.geometry import box
from app.schemas import HouseSpecification,RoomRequirement
from app.modern_home import ModernHomeLayoutEngine
from app.layout import validate,bounds
from app.services import demo_spec
from app.stair_geometry import landing_zone,stair_boxes

@pytest.mark.parametrize('road',['north','south','east','west'])
@pytest.mark.parametrize('bedrooms',[1,2,3])
def test_duplex_has_independent_stairwell_landings_and_public_route(road,bedrooms):
    w,l=(50,30) if road in ('east','west') else (30,50)
    spec=HouseSpecification(plot_width=w,plot_length=l,floors=2,road_location=road,parking_spaces=1,rooms=[RoomRequirement(type=k,name=k,count=bedrooms if k=='bedroom' else 1) for k in ('living','dining','kitchen','bedroom','bathroom')])
    layout=ModernHomeLayoutEngine().generate(spec)
    assert not [c.name for c in validate(layout,spec) if c.status=='ERROR']
    parking=next(r for r in layout.rooms if r.type=='parking');assert bounds(parking).area==180
    stair=layout.stairs[0];zone=box(stair.x,stair.y,stair.x+stair.width,stair.y+stair.length)
    assert all(bounds(r).intersection(zone).area<1e-6 for r in layout.rooms if r.type!='stair')
    assert all(r.floor==0 for r in layout.rooms if r.type in ('living','dining','kitchen'))
    assert len(list(stair_boxes(stair)))==17
    # Removing the landing must fail even though a room-adjacency graph might remain connected.
    bad=layout.model_copy(deep=True);bad.rooms=[r for r in bad.rooms if r.id!='landing-1']
    assert any(c.status=='ERROR' and c.name=='Level stair landing on floor 2' for c in validate(bad,spec))
    bad=layout.model_copy(deep=True);hall=next(r for r in bad.rooms if r.id=='landing-0')
    hall.polygon=[(stair.x,stair.y),(stair.x+stair.width,stair.y),(stair.x+stair.width,stair.y+stair.length),(stair.x,stair.y+stair.length)]
    assert any(c.status=='ERROR' and c.name=='Stairwell reserved without room overlap' for c in validate(bad,spec))

def test_original_demo_keeps_ensuites_and_clear_stair():
    spec=demo_spec();assert ModernHomeLayoutEngine.supports(spec)
    layout=ModernHomeLayoutEngine().generate(spec)
    assert len([r for r in layout.rooms if r.attached_to])==3
    assert len([r for r in layout.rooms if r.type=='bedroom'])==4
    assert not [c for c in layout.checks if c.status=='ERROR']

def test_single_storey_remains_stair_free():
    from app.simple_home import SimpleHomeLayoutEngine
    spec=HouseSpecification(plot_width=30,plot_length=40,floors=1,rooms=[RoomRequirement(type=k,name=k,count=2 if k=='bedroom' else 1) for k in ('living','kitchen','dining','bedroom','bathroom')])
    layout=SimpleHomeLayoutEngine().generate(spec)
    assert not layout.stairs
