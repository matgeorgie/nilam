"""Repeatable geometry, architecture, requirements, plot and diversity metrics."""
from collections import Counter
from ..footprint import footprint_polygon
from ..layout import validate
from ..schemas import HouseLayout, HouseSpecification, HouseShape


def classify_footprint(layout:HouseLayout) -> str:
    if not layout.footprint:return 'unknown'
    if layout.footprint.shape==HouseShape.COURTYARD:return 'courtyard'
    if layout.footprint.shape==HouseShape.STEPPED:return 'stepped'
    return layout.footprint.shape.value


def evaluate_layout(layout:HouseLayout,spec:HouseSpecification) -> dict:
    checks=validate(layout,spec);errors=[c for c in checks if c.status=='ERROR'];warnings=[c for c in checks if c.status=='WARNING']
    footprint=footprint_polygon(layout.footprint)
    return {'valid':not errors,'score':layout.score.overall_score if layout.score else 0,'shape':classify_footprint(layout),'footprint_area':round(footprint.area,2),'room_count':len([r for r in layout.rooms if r.type not in ('hall','stair')]),'violations':[c.model_dump() for c in errors],'warnings':[c.model_dump() for c in warnings]}


def diversity_report(layouts:list[HouseLayout]) -> dict:
    counts=Counter(classify_footprint(layout) for layout in layouts);total=max(1,len(layouts));rectangles=counts['rectangle']
    return {'total':len(layouts),'categories':dict(sorted(counts.items())),'rectangle_ratio':round(rectangles/total,4),'passes':rectangles/total<.95}
