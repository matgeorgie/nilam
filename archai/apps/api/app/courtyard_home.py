"""A constrained two-storey courtyard plan with a living-first entrance.

This is a deterministic layout profile for a narrow brief, not an AI model or
an architectural approval. Unsupported briefs stay with the general engine.
"""

from collections import Counter
from time import perf_counter

from .footprint import generate_footprint
from .layout import (
    InfeasibleLayout, MIN_AREA, add_door, build_walls, physically_open_pairs,
    road_edge, score, shared_wall, validate, vehicle_gate_wall, wall_line,
)
from .schemas import Check, HouseLayout, HouseShape, RoomGeometry, Stair, Window


class CourtyardHomeLayoutEngine:
    @staticmethod
    def supports(spec):
        counts = Counter({kind: sum(r.count for r in spec.rooms if r.type == kind)
                          for kind in {r.type for r in spec.rooms}})
        scale = 3.280839895 if spec.unit == 'meters' else 1
        usable_width = (spec.plot_width - spec.setbacks.left_setback - spec.setbacks.right_setback) * scale if spec.plot_width else 0
        usable_length = (spec.plot_length - spec.setbacks.front_setback - spec.setbacks.rear_setback) * scale if spec.plot_length else 0
        base = (
            spec.floors == 2 and spec.shape == HouseShape.COURTYARD
            and spec.plot_polygon is None and spec.road_location == 'north'
            and usable_width >= 40 and usable_length >= 60
            and set(counts) <= {'bedroom', 'bathroom', 'living', 'dining', 'kitchen', 'utility'}
            and spec.parking_spaces == 1
            and counts['dining'] == counts['kitchen'] == counts['utility'] == 1
            and spec.preferences.get('open_kitchen') is not False
            and all(r.exact_width is None and r.exact_length is None for r in spec.rooms)
        )
        if not base:
            return False
        single = (
            counts['bedroom'] == counts['bathroom'] == counts['living'] == 1
            and next(r for r in spec.rooms if r.type == 'bedroom').attached_bathroom
            and all(r.preferred_floor is None for r in spec.rooms)
        )
        family = (
            counts['bedroom'] == 4 and counts['bathroom'] == 3 and counts['living'] == 2
            and sum(r.count for r in spec.rooms if r.type == 'bedroom' and r.attached_bathroom) == 1
            and sum(r.count for r in spec.rooms if r.type == 'bedroom' and r.preferred_floor == 0) == 1
            and sum(r.count for r in spec.rooms if r.type == 'bedroom' and r.preferred_floor == 1) == 3
            and sum(r.count for r in spec.rooms if r.type == 'bathroom' and r.preferred_floor == 0) == 1
            and sum(r.count for r in spec.rooms if r.type == 'bathroom' and r.preferred_floor == 1) == 2
            and sum(r.count for r in spec.rooms if r.type == 'living' and r.preferred_floor == 0) == 1
            and sum(r.count for r in spec.rooms if r.type == 'living' and r.preferred_floor == 1) == 1
            and all(r.preferred_floor in (None, 0) for r in spec.rooms if r.type in ('dining', 'kitchen', 'utility'))
        )
        return single or family

    def generate(self, spec, candidate_evaluator=None):
        if sum(r.count for r in spec.rooms if r.type == 'bedroom') == 4:
            return self._generate_family(spec, candidate_evaluator)
        start = perf_counter()
        scale = 3.280839895 if spec.unit == 'meters' else 1
        width, length = spec.plot_width * scale, spec.plot_length * scale
        setbacks = spec.setbacks.model_copy(deep=True)
        if spec.unit == 'meters':
            for name in ('front_setback', 'rear_setback', 'left_setback', 'right_setback'):
                setattr(setbacks, name, getattr(setbacks, name) * scale)
        footprint = generate_footprint(spec.shape, width, length, spec.shape_parameters, setbacks)
        bx, by, maxx, maxy = footprint.bounding_box
        bw, bl = footprint.metrics['W'], footprint.metrics['L']
        side, end = footprint.metrics['side_w'], footprint.metrics['end_l']
        left = bx + side - 4
        right = bx + bw - side + 4
        middle_start, middle_end = by + end, by + bl - end
        # The car must have a full 18-foot approach depth, not merely its area.
        if min(left - bx, maxx - right) < 12 or end < 18 or middle_end - middle_start < 24:
            raise InfeasibleLayout('This courtyard is too narrow for a car porch, public rooms and private circulation.')

        requests = {r.type: r for r in spec.rooms}
        rooms = []
        def add(room_id, kind, name, floor, x1, y1, x2, y2, attached_to=None):
            req = requests.get(kind)
            minimum = max(MIN_AREA.get(kind, 0), (req.minimum_area or 0) * scale * scale) if req else 0
            room = RoomGeometry(id=room_id, name=name, type=kind, floor=floor,
                                x=x1, y=y1, width=x2-x1, height=y2-y1,
                                attached_to=attached_to, minimum_area=minimum)
            if room.width * room.height + .01 < minimum:
                raise InfeasibleLayout(f'{name} cannot meet its requested minimum area in this courtyard.')
            rooms.append(room)
            return room

        parking = add('parking-1', 'parking', 'Open car porch', 0, bx, by, left, middle_start)
        porch_depth = max(5.0, 50.0/(maxx-left))
        porch = add('porch-1', 'porch', 'Entrance sit-out', 0,
                    left, by, maxx, by+porch_depth)
        living = add('living-1', 'living', requests['living'].name, 0,
                     left, by+porch_depth, maxx, middle_start)
        hall0 = add('hall-0-0', 'hall', 'Private circulation', 0, left, middle_start, left+4, middle_end)
        hall1 = add('hall-1-0', 'hall', 'Private circulation', 1, left, middle_start, left+4, middle_end)
        right_hall = add('hall-0-1', 'hall', 'Bathroom circulation', 0, right-4, middle_start, right, middle_end)
        stair0 = add('stair-0', 'stair', 'Staircase', 0, left, middle_start, left+4, middle_start+12)
        add('stair-1', 'stair', 'Staircase', 1, left, middle_start, left+4, middle_start+12)
        zone = middle_end - middle_start
        dining_end = middle_start + zone * 10 / 24
        kitchen_end = middle_start + zone * 20 / 24
        dining = add('dining-1', 'dining', requests['dining'].name, 0, bx, middle_start, left, dining_end)
        kitchen = add('kitchen-1', 'kitchen', requests['kitchen'].name, 0, bx, dining_end, left, kitchen_end)
        utility = add('utility-1', 'utility', requests['utility'].name, 0, bx, kitchen_end, left, middle_end)
        bathroom = add('bathroom-1', 'bathroom', requests['bathroom'].name, 0, right, middle_start+zone/2, maxx, middle_start+zone*5/6)
        bedroom = add('bedroom-1', 'bedroom', requests['bedroom'].name, 1, bx, middle_start, left, middle_end)
        bath = add('bedroom-1-bath', 'bathroom', requests['bedroom'].name+' bath', 1,
                   bx, middle_start-4, left, middle_start, attached_to=bedroom.id)
        layout = HouseLayout(width=width, length=length, floors=2, footprint=footprint,
                             plot_boundary=[(0,0),(width,0),(width,length),(0,length)],
                             setback_boundary=footprint.buildable_boundary or [],
                             road_edge=road_edge('north', width, length),
                             strategy='COURTYARD_HOME', rooms=rooms, walls=[], doors=[], windows=[],
                             stairs=[Stair(id='stairs-0', from_floor=0, to_floor=1,
                                           x=left, y=middle_start, width=4, length=12)])
        open_pair = tuple(sorted((dining.id, kitchen.id)))
        build_walls(layout, spec, extra_open_pairs={open_pair})

        def connect(a, b, door_width=2.6):
            walls = shared_wall(layout, a, b)
            if not walls:
                raise InfeasibleLayout(f'{a.name} and {b.name} have no shared door wall.')
            wall = max(walls, key=lambda item: wall_line(item).length)
            add_door(layout, a, b, wall, width=min(door_width, wall_line(wall).length-.4))

        connect(living, hall0, 3)
        connect(porch, living, 3.2)
        connect(living, right_hall, 3)
        connect(hall0, dining, 3)
        connect(kitchen, utility)
        connect(right_hall, bathroom)
        connect(hall1, bedroom, 3)
        connect(bedroom, bath)
        front = [w for w in shared_wall(layout, porch, exterior=True)
                 if abs(w.y1-by) < .001 and abs(w.y2-by) < .001]
        if not front:
            raise InfeasibleLayout('No separate road-facing entrance sit-out fits.')
        add_door(layout, porch, None, max(front, key=lambda w: wall_line(w).length), width=3.2)
        gate = vehicle_gate_wall(layout, parking, 'north')
        if not gate or wall_line(gate).length < 10:
            raise InfeasibleLayout('The car porch has no adequate road-facing gate.')
        add_door(layout, parking, None, gate, width=9, kind='vehicle')
        for room in (living, dining, kitchen, utility, bathroom, bedroom, bath):
            exterior = [w for w in shared_wall(layout, room, exterior=True)
                        if not any(d.wall == w.id for d in layout.doors)]
            if exterior:
                wall = max(exterior, key=lambda w: wall_line(w).length)
                opening = min(4, wall_line(wall).length-1)
                if opening >= 2:
                    layout.windows.append(Window(id=f'window-{room.id}', room=room.id, wall=wall.id,
                                                 position=(wall_line(wall).length-opening)/2, width=opening))

        checks = validate(layout, spec)
        checks.extend([
            Check(name='Sit-out leads to living', status='PASS',
                  detail='The separate front entry opens to a sit-out, then living and dining.'),
            Check(name='Dining and kitchen are open together',
                  status='PASS' if open_pair in physically_open_pairs(layout) else 'ERROR',
                  detail='Their shared boundary has no wall or door.'),
            Check(name='Car porch has no interior shortcut',
                  status='PASS' if not any(d.room_a == parking.id and d.room_b for d in layout.doors) else 'ERROR',
                  detail='The pedestrian front entry is independent of vehicle parking.'),
        ])
        bonus = 0.0
        if candidate_evaluator and not any(c.status == 'ERROR' for c in checks):
            intent_checks, bonus = candidate_evaluator(layout)
            checks.extend(intent_checks)
        if any(c.status == 'ERROR' for c in checks):
            raise InfeasibleLayout(', '.join(c.name for c in checks if c.status == 'ERROR'))
        layout.checks = checks
        layout.score = score(layout, spec)
        layout.score.overall_score = round(min(100, layout.score.overall_score + bonus), 1)
        layout.candidate_count = 1
        layout.chosen_candidate_id = 'courtyard-home-1'
        layout.generation_ms = round((perf_counter()-start)*1000, 2)
        return layout

    def _generate_family(self, spec, candidate_evaluator):
        """Ground public rooms and one suite; three bedrooms upstairs."""
        start = perf_counter()
        scale = 3.280839895 if spec.unit == 'meters' else 1
        width, length = spec.plot_width * scale, spec.plot_length * scale
        setbacks = spec.setbacks.model_copy(deep=True)
        if spec.unit == 'meters':
            for name in ('front_setback', 'rear_setback', 'left_setback', 'right_setback'):
                setattr(setbacks, name, getattr(setbacks, name) * scale)
        footprint = generate_footprint(spec.shape, width, length, spec.shape_parameters, setbacks)
        bx, by, maxx, maxy = footprint.bounding_box
        bw, bl = footprint.metrics['W'], footprint.metrics['L']
        side, end = footprint.metrics['side_w'], footprint.metrics['end_l']
        left, right = bx + side - 4, bx + bw - side + 4
        mid_start, mid_end = by + end, by + bl - end
        if min(left-bx, maxx-right) < 12 or end < 18 or mid_end-mid_start < 24 or bl-mid_end < 18:
            raise InfeasibleLayout('The courtyard cannot fit the requested four-bedroom circulation and 18-foot car porch.')
        requests = {kind: [r for r in spec.rooms if r.type == kind]
                    for kind in ('bedroom', 'bathroom', 'living', 'dining', 'kitchen', 'utility')}
        ground_bed = next(r for r in requests['bedroom'] if r.preferred_floor == 0)
        upper_bedrooms = [r for r in requests['bedroom'] if r.preferred_floor == 1]
        ground_living = next(r for r in requests['living'] if r.preferred_floor == 0)
        upper_living = next(r for r in requests['living'] if r.preferred_floor == 1)
        ground_bath = next(r for r in requests['bathroom'] if r.preferred_floor == 0)
        upper_bath = next(r for r in requests['bathroom'] if r.preferred_floor == 1)
        rooms = []
        def add(room_id, kind, name, floor, x1, y1, x2, y2, req=None, attached_to=None):
            minimum = max(MIN_AREA.get(kind, 0), (req.minimum_area or 0) * scale * scale) if req else MIN_AREA.get(kind, 0)
            room = RoomGeometry(id=room_id, name=name, type=kind, floor=floor,
                                x=x1, y=y1, width=x2-x1, height=y2-y1,
                                attached_to=attached_to, minimum_area=minimum)
            if room.width * room.height + .01 < minimum:
                raise InfeasibleLayout(f'{name} cannot meet its requested minimum area in this courtyard.')
            rooms.append(room)
            return room

        parking = add('parking-1', 'parking', 'Open car porch', 0, bx, by, left, mid_start)
        porch_depth = max(5.0, 50.0/(maxx-left))
        porch = add('porch-1', 'porch', 'Entrance sit-out', 0,
                    left, by, maxx, by+porch_depth)
        living = add('living-1', 'living', ground_living.name, 0,
                     left, by+porch_depth, maxx, mid_start, ground_living)
        hall0 = add('hall-0-0', 'hall', 'Private circulation', 0, left, mid_start, left+4, mid_end)
        hall0_right = add('hall-0-1', 'hall', 'Bedroom and bathroom corridor', 0,
                          right-4, mid_start, right, mid_end+12)
        stair0 = add('stair-0', 'stair', 'Staircase', 0, left, mid_start, left+4, mid_start+12)
        front_hall = add('hall-1-0', 'hall', 'Upper landing', 1, bx, by+end-4, maxx, mid_start)
        hall1 = add('hall-1-1', 'hall', 'Upper circulation', 1, left, mid_start, left+4, mid_end)
        hall1_right = add('hall-1-2', 'hall', 'Bathroom circulation', 1,
                          right-4, mid_start, right, mid_end)
        add('stair-1', 'stair', 'Staircase', 1, left, mid_start, left+4, mid_start+12)
        zone = mid_end-mid_start
        dining_end = mid_start+zone*10/24
        kitchen_end = mid_start+zone*20/24
        dining = add('dining-1', 'dining', requests['dining'][0].name, 0,
                     bx, mid_start, left, dining_end, requests['dining'][0])
        kitchen = add('kitchen-1', 'kitchen', requests['kitchen'][0].name, 0,
                      bx, dining_end, left, kitchen_end, requests['kitchen'][0])
        utility = add('utility-1', 'utility', requests['utility'][0].name, 0,
                      bx, kitchen_end, left, mid_end, requests['utility'][0])
        master = add('bedroom-1', 'bedroom', ground_bed.name, 0,
                     right, mid_start, maxx, mid_end-6, ground_bed)
        master_bath = add('bedroom-1-bath', 'bathroom', ground_bed.name+' bath', 0,
                          right, mid_end-6, maxx, mid_end, attached_to=master.id)
        common = add('bathroom-1', 'bathroom', ground_bath.name, 0,
                     right, mid_end+4, maxx, mid_end+12, ground_bath)
        front_width = bw/3
        front_x = [bx, bx+front_width, bx+2*front_width, maxx]
        bedrooms = []
        for i in range(3):
            req = upper_bedrooms[i] if len(upper_bedrooms) == 3 else upper_bedrooms[0]
            bedrooms.append(add(f'bedroom-{i+2}', 'bedroom', req.name if req.count == 1 else f'{req.name} {i+2}',
                                1, front_x[i], by, front_x[i+1], by+end-4, req))
        lounge = add('living-2', 'living', upper_living.name, 1,
                     bx, mid_start, left, mid_end, upper_living)
        upper_baths = []
        for i in range(2):
            y1 = mid_start+zone*(i*7/24)
            y2 = mid_start+zone*((i+1)*7/24)
            upper_baths.append(add(f'bathroom-{i+2}', 'bathroom',
                                   upper_bath.name if upper_bath.count == 1 else f'{upper_bath.name} {i+1}',
                                   1, right, y1, maxx, y2, upper_bath))

        layout = HouseLayout(width=width, length=length, floors=2, footprint=footprint,
                             plot_boundary=[(0,0),(width,0),(width,length),(0,length)],
                             setback_boundary=footprint.buildable_boundary or [],
                             road_edge=road_edge('north', width, length),
                             strategy='COURTYARD_HOME', rooms=rooms, walls=[], doors=[], windows=[],
                             stairs=[Stair(id='stairs-0', from_floor=0, to_floor=1,
                                           x=left, y=mid_start, width=4, length=12)])
        open_pairs = {
            tuple(sorted((dining.id, kitchen.id))),
            tuple(sorted((front_hall.id, hall1.id))),
            tuple(sorted((front_hall.id, hall1_right.id))),
            tuple(sorted((front_hall.id, lounge.id))),
        }
        build_walls(layout, spec, extra_open_pairs=open_pairs)
        def connect(a, b, door_width=2.6):
            walls = shared_wall(layout, a, b)
            if not walls:
                raise InfeasibleLayout(f'{a.name} and {b.name} have no shared door wall.')
            wall = max(walls, key=lambda item: wall_line(item).length)
            add_door(layout, a, b, wall, width=min(door_width, wall_line(wall).length-.4))
        connect(living, hall0, 3)
        connect(porch, living, 3.2)
        connect(living, hall0_right, 3)
        connect(hall0, dining, 3)
        connect(kitchen, utility)
        connect(hall0_right, master)
        connect(master, master_bath)
        connect(hall0_right, common)
        for room in bedrooms:
            connect(front_hall, room)
        for room in upper_baths:
            connect(hall1_right, room)
        front = [w for w in shared_wall(layout, porch, exterior=True)
                 if abs(w.y1-by) < .001 and abs(w.y2-by) < .001]
        if not front:
            raise InfeasibleLayout('The entrance sit-out has no road-facing front door.')
        add_door(layout, porch, None, max(front, key=lambda w: wall_line(w).length), width=3.2)
        gate = vehicle_gate_wall(layout, parking, 'north')
        if not gate or wall_line(gate).length < 10:
            raise InfeasibleLayout('The car porch has no usable road-facing vehicle access.')
        add_door(layout, parking, None, gate, width=9, kind='vehicle')
        for room in (living, dining, kitchen, utility, master, master_bath, common,
                     *bedrooms, lounge, *upper_baths):
            exterior = [w for w in shared_wall(layout, room, exterior=True)
                        if not any(d.wall == w.id for d in layout.doors)]
            if exterior:
                wall = max(exterior, key=lambda w: wall_line(w).length)
                opening = min(4, wall_line(wall).length-1)
                if opening >= 2:
                    layout.windows.append(Window(id=f'window-{room.id}', room=room.id, wall=wall.id,
                                                 position=(wall_line(wall).length-opening)/2, width=opening))
        checks = validate(layout, spec)
        bonus = 0.0
        if candidate_evaluator and not any(c.status == 'ERROR' for c in checks):
            intent_checks, bonus = candidate_evaluator(layout)
            checks.extend(intent_checks)
        if any(c.status == 'ERROR' for c in checks):
            raise InfeasibleLayout(', '.join(c.name for c in checks if c.status == 'ERROR'))
        layout.checks = checks
        layout.score = score(layout, spec)
        layout.score.overall_score = round(min(100, layout.score.overall_score+bonus), 1)
        layout.candidate_count = 1
        layout.chosen_candidate_id = 'courtyard-family-1'
        layout.generation_ms = round((perf_counter()-start)*1000, 2)
        return layout
