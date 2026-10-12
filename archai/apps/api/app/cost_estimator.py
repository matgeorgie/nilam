"""Kerala concept-stage house budget from saved ArchAI room geometry.

The published observations below are prices of inputs, not a contractor BOQ.
They adjust a broad Kerala residential rate band; they cannot price site-specific
foundations, approvals, access, or a chosen brand of finishes.
"""

from datetime import date
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .schemas import HouseLayout, HouseSpecification


DISTRICTS = (
    'Kasaragod', 'Kannur', 'Wayanad', 'Kozhikode', 'Malappuram', 'Palakkad',
    'Thrissur', 'Ernakulam', 'Idukki', 'Kottayam', 'Alappuzha',
    'Pathanamthitta', 'Kollam', 'Thiruvananthapuram',
)

# DES Kerala, Q4 2025-26, district order above. INR per 50 kg cement bag,
# metric ton of 12 mm TMT, 1,000 six-inch AAC blocks, and daily labour wages.
# Source: https://ecostat.kerala.gov.in/storage/publications/1918.pdf
_CEMENT = (350, 365, 392.5, 400, 332.5, 370, 328, 350, 340, 360, 385, 330, 335, 330)
_TMT = (67000, 65500, 70000, 84500, 81000, 81500, 74000, 57500, 65500, 67000, 70500, 65250, 70500, 69925)
_BLOCK = (92000, 94500, 92500, 98500, 97500, 95000, 98250, 110000, 91500, 93000, 97500, 98750, 106000, 107750)
_MASON = (1200, 1300, 1250, 1100, 1200, 1100, 1200, 1200, 1300, 1200, 1200, 1200, 1200, 1200)
_CARPENTER = (1200, 1300, 1200, 1100, 1200, 1100, 1200, 1250, 1300, 1200, 1250, 1200, 1200, 1250)
_PLUMBER = (1000, 1200, 950, 1100, 1200, 1000, 1200, 1300, 1100, 1000, 1100, 1100, 1100, 1250)
_ELECTRICIAN = (1000, 1200, 950, 1100, 1200, 1100, 1200, 1300, 1100, 1000, 1100, 1100, 1100, 1200)
_UNSKILLED = (900, 900, 650, 900, 950, 850, 950, 950, 900, 900, 1000, 800, 900, 1000)

# Indicative 2026 Kerala turnkey residential bands, INR per covered sq ft.
# Published bands are not quotes for this plot or the ArchAI drawing.
RATE_BANDS = {
    'essential': (1800, 2000, 2200),
    'standard': (2200, 2500, 2800),
    'premium': (3000, 3750, 4500),
}
SEMI_OPEN_TYPES = {'parking', 'porch', 'veranda', 'balcony', 'sitout', 'carport'}
BATHROOM_TYPES = {'bathroom', 'attached_bathroom', 'common_bathroom', 'toilet'}
COMPLEX_SHAPES = {'l_shape', 't_shape', 'u_shape', 'c_shape', 'stepped', 'courtyard'}


def _ratio(values: tuple[float, ...], district_index: int) -> float:
    return values[district_index] / (sum(values) / len(values))


def district_factor(district: str | None) -> float:
    """Modest input-price proxy, capped to avoid pretending to be a local quote."""
    if district not in DISTRICTS:
        return 1.0
    index = DISTRICTS.index(district)
    labour = sum(_ratio(values, index) for values in
                 (_MASON, _CARPENTER, _PLUMBER, _ELECTRICIAN, _UNSKILLED)) / 5
    raw = .35 * labour + .20 * _ratio(_CEMENT, index) + .25 * _ratio(_TMT, index) + .20 * _ratio(_BLOCK, index)
    return round(max(.92, min(1.08, raw)), 4)


def _room_polygon(room):
    polygon = Polygon(room.polygon)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon if not polygon.is_empty else Polygon()


def estimate_cost(layout: HouseLayout, specification: HouseSpecification,
                  finish: str = 'standard', district: str | None = None) -> dict:
    if finish not in RATE_BANDS:
        raise ValueError('Finish must be essential, standard, or premium.')
    if district is not None and district not in DISTRICTS:
        raise ValueError('Choose one of Kerala’s 14 districts.')
    site_district = specification.site_context.district if specification.site_context else None
    resolved_district = district or (site_district if site_district in DISTRICTS else None)
    factor = district_factor(resolved_district)
    floor_areas = []
    enclosed_total = 0.0
    semi_open_total = 0.0
    gross_area = 0.0
    footprint_area = None
    if layout.footprint:
        boundary = Polygon(layout.footprint.boundary)
        if boundary.is_valid and not boundary.is_empty:
            footprint_area = boundary.area
            if layout.footprint.courtyard:
                courtyard = Polygon(layout.footprint.courtyard)
                if courtyard.is_valid:
                    footprint_area -= boundary.intersection(courtyard).area
    if footprint_area is None:
        footprint_area = layout.width * layout.length
    for floor in range(layout.floors):
        rooms = [room for room in layout.rooms if room.floor == floor]
        enclosed = unary_union([_room_polygon(room) for room in rooms if room.type not in SEMI_OPEN_TYPES])
        semi_open = unary_union([_room_polygon(room) for room in rooms if room.type in SEMI_OPEN_TYPES])
        net_enclosed = enclosed.area
        exposed_semi_open = semi_open.difference(enclosed).area
        floor_gross = min(net_enclosed * 1.10,
                          max(net_enclosed, footprint_area - exposed_semi_open))
        enclosed_total += net_enclosed
        gross_area += floor_gross
        semi_open_total += exposed_semi_open
        floor_areas.append({
            'floor': floor,
            'net_enclosed_sqft': round(net_enclosed),
            'gross_enclosed_sqft': round(floor_gross),
            'semi_open_sqft': round(exposed_semi_open),
        })
    if enclosed_total <= 0:
        raise ValueError('A saved layout with enclosed rooms is needed for an estimate.')

    # Room polygons describe usable space, not wall thickness. Add up to ten
    # percent for walls, but never charge wall area beyond the saved footprint.
    # Semi-open areas use 45% of the residential rate and stay separate.
    equivalent_area = gross_area + semi_open_total * .45
    low_rate, mid_rate, high_rate = RATE_BANDS[finish]
    bath_count = sum(room.type in BATHROOM_TYPES for room in layout.rooms)
    kitchen_count = sum(room.type == 'kitchen' for room in layout.rooms)
    extra_baths = max(0, bath_count - 2)
    extra_kitchens = max(0, kitchen_count - 1)
    # Fit-out allowances beyond the two bathrooms and one kitchen assumed in
    # the selected residential band. These are planning inputs, not DES prices.
    fitout = extra_baths * 50000 + extra_kitchens * 100000
    shape = specification.shape.value if hasattr(specification.shape, 'value') else str(specification.shape)
    complexity_rate = .03 if shape in COMPLEX_SHAPES else 0.0

    def priced(rate):
        base = equivalent_area * rate * factor
        complexity = base * complexity_rate
        construction = base + complexity + fitout
        reserve = construction * .12
        return base, complexity, construction, reserve, construction + reserve

    low = priced(low_rate)
    mid = priced(mid_rate)
    high = priced(high_rate)
    enclosed_amount = round(gross_area * mid_rate * factor)
    semi_open_amount = round(semi_open_total * .45 * mid_rate * factor)
    complexity_amount = round(mid[1])
    construction_amount = enclosed_amount + semi_open_amount + fitout + complexity_amount
    reserve_amount = round(construction_amount * .12)
    return {
        'as_of': date.today().isoformat(),
        'district': resolved_district,
        'district_source': 'selected' if district else ('nilam' if site_district in DISTRICTS else 'kerala_average'),
        'district_factor': factor,
        'finish': finish,
        'rate_band_inr_sqft': {'low': low_rate, 'mid': mid_rate, 'high': high_rate},
        'floors': floor_areas,
        'area': {
            'net_enclosed_sqft': round(enclosed_total),
            'gross_enclosed_sqft': round(gross_area),
            'wall_allowance_sqft': round(gross_area - enclosed_total),
            'semi_open_sqft': round(semi_open_total),
            'priced_equivalent_sqft': round(equivalent_area),
        },
        'requirements': {'bathrooms': bath_count, 'kitchens': kitchen_count, 'shape': shape},
        'line_items': [
            {'label': 'Enclosed home', 'detail': f'{round(gross_area):,} sq ft × regional rate', 'amount_inr': enclosed_amount},
            {'label': 'Porches, balconies & parking', 'detail': f'{round(semi_open_total):,} sq ft × 45% rate', 'amount_inr': semi_open_amount},
            {'label': 'Additional wet-area fit-out', 'detail': f'{extra_baths} bathroom(s) beyond two; {extra_kitchens} kitchen(s) beyond one', 'amount_inr': fitout},
            {'label': 'Plan complexity allowance', 'detail': '3% for non-rectangular plan' if complexity_rate else 'No plan-shape uplift', 'amount_inr': complexity_amount},
        ],
        'construction_inr': construction_amount,
        'reserve_inr': reserve_amount,
        'planning_budget_inr': construction_amount + reserve_amount,
        'planning_range_inr': {'low': round(low[4]), 'high': round(high[4])},
        'assumptions': [
            'Residential rates include ordinary structure, standard electrical and plumbing work, and finish quality at the chosen level.',
            'Up to 10% is added to usable room polygons for walls, capped by the saved footprint; semi-open space is priced at 45% of the residential rate.',
            'Selected rate assumes up to two bathrooms and one kitchen. Further fit-out is a concept-stage allowance.',
            'A 12% reserve is added to the construction estimate. Plot-specific foundation and external works are not measured.',
        ],
        'exclusions': [
            'Land purchase, registration, taxes, loans and finance costs',
            'Soil testing, special foundations, retaining walls, flood raising and slope stabilisation',
            'Approvals, professional fees, boundary wall, landscaping, utility connections and furnishings',
        ],
        'sources': [
            {'title': 'Kerala DES · Q4 2025–26 material prices and labour wages', 'url': 'https://ecostat.kerala.gov.in/storage/publications/1918.pdf', 'use': 'district input-price adjustment'},
            {'title': 'Mezmerix · Kerala house construction cost 2026', 'url': 'https://mezmerix.in/blog-house-construction-cost-kerala', 'use': 'indicative residential rate bands'},
            {'title': 'K Jasons · Kerala construction cost 2026', 'url': 'https://kjasons.com/2026/08/29/house-construction-cost-in-kerala-2026/', 'use': 'rate-band cross-check'},
        ],
        'method': 'Concept-stage planning estimate from the current saved ArchAI revision. A local itemised quotation is needed before contracting.',
    }
