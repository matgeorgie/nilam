import asyncio
from collections import Counter
from shapely.geometry import Polygon
from app.ai.providers import MockAIProvider,is_full_design_brief
from app.schemas import HouseSpecification
from app.simple_home import SimpleHomeLayoutEngine
from app.layout import bounds,validate
BRIEF='Design a modern single-floor courtyard-shaped home on a 50 × 60 ft plot, with the road on the north. Include 3 bedrooms, 2 shared bathrooms, a living room, dining area, kitchen, utility room, a front sit-out, and parking for one car. Arrange the rooms around a central open-to-sky courtyard. Connect living and dining, and place the kitchen beside dining. Keep bedrooms in a quieter wing, accessible from a passage without walking through another bedroom. Provide windows facing the courtyard or outside. Keep parking separate from pedestrian circulation. No staircase is needed.'

def test_exact_single_floor_courtyard_brief():
    assert is_full_design_brief(BRIEF)
    spec=asyncio.run(MockAIProvider().extract(BRIEF,HouseSpecification(plot_width=30,plot_length=50,floors=2))).specification
    assert spec.floors==1 and spec.plot_width==50 and spec.plot_length==60
    assert sum(r.count for r in spec.rooms if r.type=='bathroom')==2
    layout=SimpleHomeLayoutEngine().generate(spec)
    assert layout.strategy=='SINGLE_COURTYARD' and not layout.stairs
    assert not [c.name for c in layout.checks if c.status=='ERROR']
    hole=Polygon(layout.footprint.courtyard)
    assert hole.area==252
    assert all(bounds(r).intersection(hole).area<1e-6 for r in layout.rooms)
    assert Counter(r.type for r in layout.rooms)['bedroom']==3
    assert any(d.kind=='courtyard' for d in layout.doors)
    broken=layout.model_copy(deep=True)
    next(d for d in broken.doors if d.kind=='courtyard').kind='entry'
    assert any(c.name=='Road to sit-out to living route' and c.status=='ERROR' for c in validate(broken,spec))
