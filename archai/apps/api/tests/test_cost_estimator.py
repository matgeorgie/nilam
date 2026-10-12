import pytest

from app.cost_estimator import DISTRICTS, district_factor, estimate_cost
from app.schemas import HouseLayout, HouseSpecification, RoomGeometry, SiteContext


def room(name, kind, x, y, width, height):
    return RoomGeometry(id=name, name=name, type=kind, floor=0,
                        x=x, y=y, width=width, height=height)


def test_estimate_uses_room_union_and_nilam_district():
    layout = HouseLayout(width=30, length=40, floors=1, rooms=[
        room('living', 'living', 0, 0, 20, 20),
        room('kitchen', 'kitchen', 15, 0, 10, 10),  # 50 sq ft overlaps living
        room('porch', 'porch', 20, 0, 10, 10),
        room('bath', 'bathroom', 0, 20, 5, 10),
    ], walls=[], doors=[], windows=[], stairs=[])
    spec = HouseSpecification(shape='l_shape', site_context=SiteContext(
        lat=10.5, lon=76.2, district='Thrissur', suitability_percent=80))
    result = estimate_cost(layout, spec)
    assert result['district'] == 'Thrissur'
    assert result['district_source'] == 'nilam'
    assert result['area']['net_enclosed_sqft'] == 500
    assert result['area']['semi_open_sqft'] == 50  # the other half overlaps the kitchen
    assert result['area']['gross_enclosed_sqft'] == 550
    assert result['area']['priced_equivalent_sqft'] == 572
    assert result['requirements']['bathrooms'] == 1
    assert result['line_items'][3]['amount_inr'] > 0
    assert sum(item['amount_inr'] for item in result['line_items']) == result['construction_inr']
    assert result['planning_range_inr']['low'] < result['planning_budget_inr'] < result['planning_range_inr']['high']


def test_finish_and_region_affect_budget_but_site_score_does_not():
    layout = HouseLayout(width=30, length=40, floors=1, rooms=[room('living', 'living', 0, 0, 20, 20)],
                         walls=[], doors=[], windows=[], stairs=[])
    spec = HouseSpecification(site_context=SiteContext(lat=10.5, lon=76.2, district='Thrissur', suitability_percent=15))
    essential = estimate_cost(layout, spec, 'essential')
    premium = estimate_cost(layout, spec, 'premium')
    other = estimate_cost(layout, spec, 'standard', 'Kozhikode')
    spec.site_context.suitability_percent = 95
    assert estimate_cost(layout, spec, 'essential')['planning_budget_inr'] == essential['planning_budget_inr']
    assert premium['planning_budget_inr'] > essential['planning_budget_inr']
    assert other['district_source'] == 'selected'
    assert other['district_factor'] == district_factor('Kozhikode')
    assert len(DISTRICTS) == 14
    assert all(.92 <= district_factor(name) <= 1.08 for name in DISTRICTS)
    with pytest.raises(ValueError):
        estimate_cost(layout, spec, district='Chennai')
    with pytest.raises(ValueError):
        estimate_cost(layout, spec, finish='gold-plated')


def test_wall_allowance_never_prices_more_than_the_saved_footprint():
    layout = HouseLayout(width=10, length=10, floors=1,
                         rooms=[room('living', 'living', 0, 0, 10, 10)],
                         walls=[], doors=[], windows=[], stairs=[])
    result = estimate_cost(layout, HouseSpecification())
    assert result['area']['gross_enclosed_sqft'] == 100
    assert result['area']['wall_allowance_sqft'] == 0
