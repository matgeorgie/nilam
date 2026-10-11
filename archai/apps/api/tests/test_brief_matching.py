import asyncio
from collections import Counter
from app.ai.providers import MockAIProvider,is_full_design_brief
from app.schemas import HouseSpecification,RoomRequirement
from app.modern_home import ModernHomeLayoutEngine
from app.layout import validate

BRIEF = 'Design a modern two-floor home on a 30 × 50 ft plot with the road on the south. On the ground floor, include a living room, dining area, kitchen, one guest bedroom, one shared bathroom, a front sit-out, and parking for one car. On the first floor, include two bedrooms, one shared bathroom, and a balcony. Place the staircase in a dedicated stairwell connected to the hall, with clear landings on both floors. Keep living and dining connected, place the kitchen beside dining, and provide bedroom access from the hall. Include exterior windows for daylight and ventilation.'

def test_exact_user_brief_is_parsed_and_planned_by_floor():
    old=HouseSpecification(plot_width=40,plot_length=60,floors=2,rooms=[RoomRequirement(type='bedroom',name='Old bedroom',count=5)])
    assert is_full_design_brief(BRIEF)
    spec=asyncio.run(MockAIProvider().extract(BRIEF,old)).specification
    actual=Counter()
    for r in spec.rooms:actual[(r.type,r.preferred_floor)]+=r.count
    assert actual=={('living',0):1,('dining',0):1,('kitchen',0):1,('bedroom',0):1,('bathroom',0):1,('bedroom',1):2,('bathroom',1):1,('balcony',1):1}
    assert (spec.plot_width,spec.plot_length,spec.road_location,spec.parking_spaces)==(30,50,'south',1)
    layout=ModernHomeLayoutEngine().generate(spec)
    assert not [c.name for c in validate(layout,spec) if c.status=='ERROR']
    for key,count in actual.items():assert sum((r.type,r.floor)==key for r in layout.rooms)==count
    bad=layout.model_copy(deep=True)
    next(r for r in bad.rooms if r.type=='bedroom' and r.floor==0).floor=1
    assert any(c.status=='ERROR' and c.name=='Ground floor: 1 bedroom' for c in validate(bad,spec))

def test_small_edit_is_not_treated_as_replacement_brief():
    for message in ['Change the plot to 30 x 50 feet','Add one guest bedroom on the ground floor','Make the kitchen larger']:
        assert not is_full_design_brief(message)
