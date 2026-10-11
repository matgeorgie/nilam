"""A measured, single-storey residential layout for a common family brief.

This is intentionally a narrow deterministic path, not a learned design model.
Unsupported briefs retain the existing candidate generator as a fallback.
"""

from collections import Counter
from time import perf_counter

from .courtyard_home import CourtyardHomeLayoutEngine
from .layout import (
    DeterministicLayoutEngine, InfeasibleLayout, MIN_AREA, add_door,
    build_walls, bounds, physically_open_pairs, road_edge, score, shared_wall,
    validate, vehicle_gate_wall, wall_line,
)
from .schemas import (
    Check, HouseFootprint, HouseLayout, HouseShape, RoomGeometry, Window,
)


class SimpleHomeLayoutEngine:
    """Prefer a coherent public-to-private plan when the brief fits this template."""

    def generate(self, spec, candidate_evaluator=None):
        from .single_courtyard import SingleCourtyardEngine
        if SingleCourtyardEngine.supports(spec):
            return SingleCourtyardEngine().generate(spec,candidate_evaluator)
        from .modern_home import ModernHomeLayoutEngine
        if ModernHomeLayoutEngine.supports(spec):
            return ModernHomeLayoutEngine().generate(spec, candidate_evaluator)
        if CourtyardHomeLayoutEngine.supports(spec):
            return CourtyardHomeLayoutEngine().generate(spec, candidate_evaluator)
        if not self.supports(spec):
            return self._fallback(spec, candidate_evaluator)
        try:
            return self._generate_simple(spec, candidate_evaluator)
        except InfeasibleLayout:
            return self._fallback(spec, candidate_evaluator)

    @staticmethod
    def _fallback(spec, candidate_evaluator):
        layout = DeterministicLayoutEngine(entry_sitout=True).generate(spec, candidate_evaluator)
        layout.strategy = 'LEGACY_FALLBACK'
        layout.checks.append(Check(name='Simple-home layout unavailable', status='WARNING',
                                   detail='This brief used the legacy corridor-based generator; review circulation and room access.'))
        return layout

    @staticmethod
    def supports(spec):
        counts = Counter({kind: sum(r.count for r in spec.rooms if r.type == kind)
                          for kind in {r.type for r in spec.rooms}})
        allowed = {'bedroom', 'bathroom', 'living', 'dining', 'kitchen', 'utility'}
        scale = 3.280839895 if spec.unit == 'meters' else 1
        return (
            spec.floors == 1 and spec.shape in (HouseShape.AUTO, HouseShape.RECTANGLE)
            and spec.road_location == 'north' and spec.plot_polygon is None
            and spec.plot_width is not None and spec.plot_length is not None
            and (spec.plot_width - spec.setbacks.left_setback - spec.setbacks.right_setback) * scale >= 38
            and (spec.plot_length - spec.setbacks.front_setback - spec.setbacks.rear_setback) * scale >= 50
            and set(counts) <= allowed and counts['bedroom'] in (2, 3)
            and counts['bathroom'] == 2 and counts['living'] == counts['dining'] == counts['kitchen'] == counts['utility'] == 1
            and spec.parking_spaces == 1 and not any(r.attached_bathroom or r.exact_width or r.exact_length or r.preferred_floor not in (None, 0) for r in spec.rooms)
            and spec.preferences.get('open_kitchen') is not False
        )

    def _generate_simple(self, spec, candidate_evaluator):
        start = perf_counter()
        scale = 3.280839895 if spec.unit == 'meters' else 1
        width, length = spec.plot_width * scale, spec.plot_length * scale
        bx, by = spec.setbacks.left_setback * scale, spec.setbacks.front_setback * scale
        usable_w = width - bx - spec.setbacks.right_setback * scale
        usable_l = length - by - spec.setbacks.rear_setback * scale
        built_l = min(usable_l, 50.0)
        x0, x1, x2, x4 = bx, bx + usable_w * .35, bx + usable_w * .35 + 4, bx + usable_w
        x3 = x2 + (x4 - x2) / 2
        y0, y1, y2, y4 = by, by + built_l * .34, by + built_l * .62, by + built_l
        y3 = (y2 + y4) / 2
        if min(x1-x0,x3-x2,x4-x3) < 8 or y3-y2 < 8:
            raise InfeasibleLayout('The simple-home zones are too narrow for safe room sizes.')

        requirements = {kind: [r for r in spec.rooms if r.type == kind]
                        for kind in ('bedroom','bathroom','living','dining','kitchen','utility')}
        def minimum(kind, index=0):
            reqs = requirements[kind]
            req = reqs[min(index, len(reqs)-1)]
            return max(MIN_AREA[kind], (req.minimum_area or 0) * scale * scale)
        def label(kind, index=0):
            reqs = requirements[kind]
            if len(reqs) > 1:
                return reqs[index].name
            return reqs[0].name + (f' {index+1}' if reqs[0].count > 1 else '')
        rooms = []
        def add(room_id, kind, name, xa, ya, xb, yb, area=0):
            room = RoomGeometry(id=room_id, name=name, type=kind, floor=0,
                                x=xa, y=ya, width=xb-xa, height=yb-ya,
                                minimum_area=area)
            if (xb-xa)*(yb-ya)+.01 < area:
                raise InfeasibleLayout(f'{name} does not fit its minimum area.')
            rooms.append(room)
            return room

        parking = add('parking-1','parking','Open car porch',x0,y0,x1,y1,160)
        porch_depth=max(5.0,50.0/(x4-x1))
        porch=add('porch-1','porch','Entrance sit-out',x1,y0,x4,y0+porch_depth,50)
        living = add('living-1','living',label('living'),x1,y0+porch_depth,x4,y1,minimum('living'))
        add('bedroom-1','bedroom',label('bedroom',0),x0,y1,x1,y2,minimum('bedroom',0))
        hall = add('hall-0-0','hall','Private circulation',x1,y1,x2,y4)
        dining = add('dining-1','dining',label('dining'),x2,y1,x3,y2,minimum('dining'))
        kitchen = add('kitchen-1','kitchen',label('kitchen'),x3,y1,x4,y2,minimum('kitchen'))
        bedroom_count = sum(r.count for r in requirements['bedroom'])
        if bedroom_count == 2:
            add('bedroom-2','bedroom',label('bedroom',1),x0,y2,x1,y4,minimum('bedroom',1))
        else:
            add('bedroom-2','bedroom',label('bedroom',1),x0,y2,x1,y3,minimum('bedroom',1))
            add('bedroom-3','bedroom',label('bedroom',2),x0,y3,x1,y4,minimum('bedroom',2))
        add('bathroom-1','bathroom',label('bathroom',0),x2,y2,x3,y3,minimum('bathroom',0))
        add('bathroom-2','bathroom',label('bathroom',1),x2,y3,x3,y4,minimum('bathroom',1))
        utility = add('utility-1','utility',label('utility'),x3,y2,x4,y4,minimum('utility'))

        footprint_boundary=[(x0,y0),(x4,y0),(x4,y4),(x0,y4)]
        setback_boundary=[(x0,y0),(x4,y0),(x4,by+usable_l),(x0,by+usable_l)]
        footprint=HouseFootprint(shape=HouseShape.RECTANGLE,plot_width=width,plot_length=length,
                                 boundary=footprint_boundary,buildable_boundary=setback_boundary,
                                 bounding_box=(x0,y0,x4,y4),
                                 metrics={'W':usable_w,'L':built_l,'footprint_area':usable_w*built_l,'buildable_area':usable_w*usable_l})
        layout=HouseLayout(width=width,length=length,floors=1,footprint=footprint,
                           plot_boundary=[(0,0),(width,0),(width,length),(0,length)],
                           setback_boundary=setback_boundary,road_edge=road_edge('north',width,length),
                           strategy='SIMPLE_HOME',rooms=rooms,walls=[],doors=[],windows=[],stairs=[])
        open_pairs={tuple(sorted((living.id,dining.id))),tuple(sorted((dining.id,kitchen.id)))}
        build_walls(layout,spec,extra_open_pairs=open_pairs)
        room_by_id={room.id:room for room in rooms}
        def connect(room_a,room_b,width=2.6):
            shared=shared_wall(layout,room_a,room_b)
            if not shared: raise InfeasibleLayout(f'No valid door wall between {room_a.name} and {room_b.name}.')
            wall=max(shared,key=lambda item:wall_line(item).length)
            add_door(layout,room_a,room_b,wall,width=min(width,wall_line(wall).length-.3))
        connect(living,hall,3)
        connect(porch,living,3.2)
        for room in rooms:
            if room.type in ('bedroom','bathroom'):
                connect(room,hall)
        connect(kitchen,utility)
        entrance=[w for w in shared_wall(layout,porch,exterior=True) if abs(w.y1-y0)<.001 and abs(w.y2-y0)<.001]
        if not entrance: raise InfeasibleLayout('No road-facing entrance sit-out.')
        add_door(layout,porch,None,max(entrance,key=lambda item:wall_line(item).length),width=3.2)
        gate=vehicle_gate_wall(layout,parking,'north')
        if not gate: raise InfeasibleLayout('The open car porch has no road-facing vehicle access.')
        add_door(layout,parking,None,gate,width=min(12,wall_line(gate).length-.4),kind='vehicle')
        for room in rooms:
            if room.type not in ('bedroom','living','kitchen','utility'): continue
            candidates=[w for w in shared_wall(layout,room,exterior=True)
                        if not any(d.wall==w.id for d in layout.doors)]
            if candidates:
                wall=max(candidates,key=lambda item:wall_line(item).length)
                opening=min(4,wall_line(wall).length-1)
                if opening>1:
                    layout.windows.append(Window(id=f'window-{room.id}',room=room.id,wall=wall.id,
                                                 position=(wall_line(wall).length-opening)/2,width=opening))

        checks=validate(layout,spec)
        checks.extend([
            Check(name='Sit-out leads to living room',status='PASS',detail='North-side entry passes through the sit-out before living.'),
            Check(name='Public rooms have open connections',status='PASS' if open_pairs <= physically_open_pairs(layout) else 'ERROR',detail='Living–dining and dining–kitchen share doorless openings.'),
            Check(name='Parking does not route through private rooms',status='PASS' if not any(d.room_a==parking.id and d.room_b for d in layout.doors) else 'ERROR',detail='Pedestrians use the separate living-room entrance.'),
        ])
        bonus=0.0
        if candidate_evaluator and not any(c.status=='ERROR' for c in checks):
            intent_checks,bonus=candidate_evaluator(layout)
            checks.extend(intent_checks)
        if any(c.status=='ERROR' for c in checks):
            raise InfeasibleLayout(', '.join(c.name for c in checks if c.status=='ERROR'))
        layout.checks=checks
        layout.score=score(layout,spec)
        layout.score.overall_score=round(min(100,layout.score.overall_score+bonus),1)
        layout.candidate_count=1
        layout.chosen_candidate_id='simple-home-1'
        layout.generation_ms=round((perf_counter()-start)*1000,2)
        return layout
