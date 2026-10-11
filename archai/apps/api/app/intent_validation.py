"""Independent deterministic acceptance and preference checks for SpatialIntent."""
from .ai.intent import CompiledIntent
from .layout import bounds, relationship_ok
from .schemas import Check, HouseLayout, Relationship


def evaluate_intent(layout: HouseLayout, compiled: CompiledIntent) -> tuple[list[Check], float]:
    rooms = {room.id: room for room in layout.rooms}
    checks = []
    soft_results = []
    for resolved in compiled.constraints:
        request = resolved.request
        room = rooms.get(resolved.room_id)
        if request.kind == 'floor_placement':
            met = bool(room and room.floor == request.floor)
        elif request.kind == 'minimum_area':
            scale = 3.280839895 if compiled.specification.unit == 'meters' else 1
            met = bool(room and bounds(room).area + .01 >= request.area * scale**2)
        elif request.kind == 'relationship':
            relation = Relationship(source=resolved.room_id, target=resolved.target_id, relation=request.relation)
            met = relationship_ok(layout, relation)
        elif request.kind == 'setbacks':
            met = next(c.status for c in layout.checks if c.name == 'Setbacks respected') == 'PASS'
        else:
            met = (compiled.specification.parking_spaces > 0 and
                   compiled.specification.road_location == request.road_side and
                   next(c.status for c in layout.checks if c.name == 'Parking has road-reachable vehicle access') == 'PASS')
        hard = request.priority == 'hard'
        checks.append(Check(name=f'Spatial intent: {request.source_text}',
                            status='PASS' if met else ('ERROR' if hard else 'WARNING'),
                            detail=f'{request.kind}; {request.priority}; deterministic check'))
        if not hard:
            soft_results.append(met)
    for request in compiled.specification.spatial_intent.unsupported_requests if compiled.specification.spatial_intent else []:
        checks.append(Check(name=f'Unsupported request: {request.text}', status='WARNING', detail=request.reason))
    bonus = 5.0 * sum(soft_results) / len(soft_results) if soft_results else 0.0
    return checks, bonus
