"""Deterministic orthogonal packing; geometry is never accepted from an LLM."""
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from math import hypot
from time import perf_counter
from shapely.geometry import box, LineString, Polygon
from shapely.ops import unary_union
from .schemas import (HouseSpecification, HouseLayout, LayoutAlternative, RoomGeometry, Wall, Door, Window, Stair, Check, LayoutScore, HouseShape, Relationship,
                        RoomCategory, RoomEnclosure, ArchitecturalRelation, default_room_category)
from .footprint import generate_footprint, footprint_polygon, validate_footprint

MIN_AREA={'bedroom':100,'bathroom':35,'kitchen':80,'dining':90,'living':140,'parking':160,'balcony':40,'office':70,'utility':35,'porch':50,'veranda':50}
MIN_SIDE={'bedroom':8,'bathroom':4,'kitchen':7,'dining':7,'living':9,'parking':8,'balcony':3,'office':7,'utility':4,'porch':4,'veranda':4}

DEFAULT_SCORE_WEIGHTS = {
    'requirement_score': 0.207,
    'adjacency_score': 0.131,
    'area_score': 0.113,
    'circulation_score': 0.113,
    'efficiency_score': 0.075,
    'lighting_score': 0.075,
    'privacy_score': 0.075,
    'ventilation_score': 0.057,
    'structural_score': 0.047,
    'plot_utilization_score': 0.047,
    'strategy_score': 0.060,
}

STRATEGIES = ['PUBLIC_FRONT', 'PUBLIC_CENTRAL', 'PRIVATE_REAR', 'SERVICE_CLUSTER', 'OPEN_PUBLIC_ZONE']

def structural_signature(layout):
    entries = []
    for r in sorted(layout.rooms, key=lambda r: (r.floor, r.id)):
        entries.append((
            r.id,
            r.type,
            r.floor,
            round(r.x, 0),
            round(r.y, 0),
            round(r.width, 0),
            round(r.height, 0),
        ))
    return hash((layout.footprint.shape.value, tuple(entries)))

class InfeasibleLayout(ValueError): pass

def bounds(r): return Polygon(r.polygon) if r.polygon else box(r.x,r.y,r.x+r.width,r.y+r.height)

def _wing_road_dist(wi, wings, side):
    wx, wy, ww, wl = wings[wi]
    if side == 'north': return wy
    if side == 'south': return -(wy + wl)
    if side == 'west': return wx
    if side == 'east': return -(wx + ww)
    return 0
def wall_line(w): return LineString([(w.x1,w.y1),(w.x2,w.y2)])

def road_edge(side,width,length):
    return {'south':((0,length),(width,length)),'north':((0,0),(width,0)),'west':((0,0),(0,length)),'east':((width,0),(width,length))}[side]

def _candidate_rationale(layout):
    shape=layout.footprint.shape.value.replace('_',' ')
    return f'{shape.title()} footprint · {layout.score.circulation_score:.0f}% circulation · {layout.score.lighting_score:.0f}% daylight · {layout.score.plot_utilization_score:.0f}% plot use'

class LayoutEngine(ABC):
    @abstractmethod
    def generate(self,spec: HouseSpecification) -> HouseLayout: ...

class DeterministicLayoutEngine(LayoutEngine):
    def __init__(self, entry_sitout=False):
        self.entry_sitout = entry_sitout

    def generate(self,spec,candidate_evaluator=None):
        start=perf_counter()
        if not spec.plot_width or not spec.plot_length or not spec.floors or not spec.rooms:
            raise InfeasibleLayout('Plot dimensions, floor count and rooms are required before generation.')
        scale=3.280839895 if spec.unit=='meters' else 1
        width,length=spec.plot_width*scale,spec.plot_length*scale
        if width<20 or length<22: raise InfeasibleLayout('This corridor layout requires a plot at least 20 × 22 ft. Increase the plot or reduce your requirements.')
        side=(width-4)/2
        units=[]
        used=Counter()
        for req in spec.rooms:
            if self.entry_sitout and req.type=='porch' and req.preferred_floor in (None,0):
                if req.count!=1:raise InfeasibleLayout('Specify one ground-floor entrance sit-out.')
                if req.exact_width or req.exact_length:raise InfeasibleLayout('Exact sit-out dimensions require a dedicated frontage layout.')
                continue  # Allocated from the road-facing living space below.
            for _ in range(req.count):
                used[req.type]+=1
                minimum=max(MIN_AREA[req.type],(req.minimum_area or 0)*scale**2)
                area=max(minimum,(req.preferred_area or minimum*1.25)*scale**2 if req.preferred_area else minimum*1.25)
                exact_h=req.exact_length*scale if req.exact_length else None
                if req.exact_width and abs(req.exact_width*scale-side)>0.01:
                    raise InfeasibleLayout(f'{req.name}: exact width {req.exact_width:g} {spec.unit} cannot fit this corridor partition ({side:.1f} ft). Change the plot width or use an area preference.')
                depth=max(area/side,MIN_SIDE[req.type])
                min_depth=max(minimum/side,MIN_SIDE[req.type])
                if exact_h:
                    if exact_h<min_depth: raise InfeasibleLayout(f'{req.name}: requested dimensions are below the minimum room size.')
                    depth=min_depth=exact_h
                bath=4.5 if req.attached_bathroom else 0
                cat=getattr(req,'category',None) or default_room_category(req.type)
                enc=getattr(req,'enclosure',None) or RoomEnclosure.ENCLOSED
                units.append({'id':f'{req.type}-{used[req.type]}','name':req.name if req.count==1 else f'{req.name} {used[req.type]}','type':req.type,'minimum':minimum,'depth':depth+bath,'min_depth':min_depth+bath,'bath':bath,'floor':req.preferred_floor,'exact':bool(exact_h),'category':cat,'enclosure':enc})
        for i in range(spec.parking_spaces):
            units.append({'id':f'parking-{i+1}','name':f'Parking {i+1}','type':'parking','minimum':160,'depth':max(18,160/side),'min_depth':max(18,160/side),'bath':0,'floor':0,'exact':False,'category':RoomCategory.SERVICE,'enclosure':RoomEnclosure.ENCLOSED})
        candidates=[]
        rejection_reasons=[]
        shapes=[spec.shape] if spec.shape!=HouseShape.AUTO else [HouseShape.RECTANGLE,HouseShape.L_SHAPE,HouseShape.T_SHAPE,HouseShape.U_SHAPE,HouseShape.C_SHAPE,HouseShape.STEPPED,HouseShape.COURTYARD]
        seen_signatures = set()
        for shape in shapes:
            for strategy in STRATEGIES:
                for sort_variant,entry_variant in ((sv,ev) for sv in (0,1)
                                                   for ev in ((0,1) if self.entry_sitout else (0,))):
                    try:
                        layout=self._candidate(spec,width,length,side,units,strategy,sort_variant,shape,entry_variant)
                        if self.entry_sitout:
                            carve_entry_sitout(layout,spec)
                        sig = structural_signature(layout)
                        if sig in seen_signatures:
                            continue
                        seen_signatures.add(sig)
                        layout.checks=validate(layout,spec)
                        bonus=0.0
                        if not any(c.status=='ERROR' for c in layout.checks) and candidate_evaluator:
                            intent_checks,bonus=candidate_evaluator(layout)
                            layout.checks.extend(intent_checks)
                        if not any(c.status=='ERROR' for c in layout.checks):
                            layout.score=score(layout,spec)
                            layout.score.overall_score=round(min(100,layout.score.overall_score+bonus),1)
                            layout.chosen_candidate_id=f'{shape.value}-{strategy}-{sort_variant}'
                            candidates.append(layout)
                        else:
                            self.last_rejected=layout
                            rejection_reasons.append(', '.join(c.name for c in layout.checks if c.status=='ERROR'))
                    except (InfeasibleLayout,ValueError) as error:
                        rejection_reasons.append(str(error))
        if not candidates:
            self.last_rejection_reasons=rejection_reasons
            reason=rejection_reasons[0] if rejection_reasons else 'no feasible candidate'
            target='candidate search' if spec.shape==HouseShape.AUTO else spec.shape.value.replace('_',' ')
            raise InfeasibleLayout(f'The {target} cannot satisfy the current requirements: {reason}. Increase the plot, reduce rooms, add a floor, or choose a footprint with more usable area.')
        best=max(candidates,key=lambda c:c.score.overall_score)
        best.candidate_count=len(candidates)
        by_shape={}
        for candidate in sorted(candidates,key=lambda c:c.score.overall_score,reverse=True):
            by_shape.setdefault(candidate.footprint.shape,candidate)
        ranked=sorted(by_shape.values(),key=lambda c:c.score.overall_score,reverse=True)[:5]
        if len(ranked)<5:
            ranked.extend(c for c in sorted(candidates,key=lambda c:c.score.overall_score,reverse=True) if c not in ranked) 
            ranked=ranked[:5]
        best.alternatives=[LayoutAlternative(candidate_id=c.chosen_candidate_id or f'candidate-{i+1}',strategy=c.strategy,label=c.footprint.shape.value.replace('_',' ').title(),rationale=_candidate_rationale(c),width=c.width,length=c.length,floors=c.floors,footprint=c.footprint,rooms=c.rooms,walls=c.walls,doors=c.doors,windows=c.windows,stairs=c.stairs,checks=c.checks,score=c.score) for i,c in enumerate(ranked)]
        best.generation_ms=round((perf_counter()-start)*1000,2)
        return best

    def get_wings_and_corridors(self, shape, m, bx, by, bw, bl):
        wings = []
        corridors = []
        width = bw
        length = bl
        if shape == HouseShape.RECTANGLE:
            side = (width - 4) / 2
            corridors.append((bx + side, by + 0, 4, length))
            wings.extend([(bx + 0, by + 0, side, length), (bx + side+4, by + 0, width-side-4, length)])
        elif shape == HouseShape.L_SHAPE:
            cx = m['arm_w'] - 4
            corridors.append((bx + cx, by + 0, 4, length))
            wings.append((bx + 0, by + 0, cx, length))
            wings.append((bx + m['arm_w'], by + 0, width - m['arm_w'], m['arm_l']))
        elif shape == HouseShape.T_SHAPE:
            cx = width / 2 - 2
            corridors.append((bx + cx, by + 0, 4, length))
            wings.append((bx + m['stem_x'], by + m['top_l'], cx - m['stem_x'], length - m['top_l']))
            wings.append((bx + cx + 4, by + m['top_l'], m['stem_x'] + m['stem_w'] - cx - 4, length - m['top_l']))
            wings.append((bx + 0, by + 0, cx, m['top_l']))
            wings.append((bx + cx + 4, by + 0, width - cx - 4, m['top_l']))
        elif shape == HouseShape.U_SHAPE:
            cy = m['rear_l'] - 4
            corridors.append((bx + 0, by + cy, width, 4))
            corridors.append((bx + m['left_w'] - 4, by + m['rear_l'], 4, length - m['rear_l']))
            corridors.append((bx + width - m['right_w'], by + m['rear_l'], 4, length - m['rear_l']))
            wings.append((bx + 0, by + 0, width, cy))
            wings.append((bx + 0, by + m['rear_l'], m['left_w'] - 4, length - m['rear_l']))
            wings.append((bx + width - m['right_w'] + 4, by + m['rear_l'], m['right_w'] - 4, length - m['rear_l']))
        elif shape == HouseShape.C_SHAPE:
            cx = m['side_w'] - 4
            corridors.append((bx + cx, by + 0, 4, length))
            wings.append((bx + 0, by + 0, cx, length))
            wings.append((bx + m['side_w'], by + 0, width - m['side_w'], m['bottom_l']))
            wings.append((bx + m['side_w'], by + length - m['top_l'], width - m['side_w'], m['top_l']))
        elif shape == HouseShape.STEPPED:
            cx=min(m['step2']-4,max(8,width*.34))
            corridors.append((bx+cx,by,4,length))
            wings.append((bx,by,cx,length))
            wings.append((bx+cx+4,by,width-cx-4,m['d1']))
            wings.append((bx+cx+4,by+m['d1'],m['step1']-cx-4,m['d2']-m['d1']))
            wings.append((bx+cx+4,by+m['d2'],m['step2']-cx-4,length-m['d2']))
        elif shape == HouseShape.COURTYARD:
            side=m['side_w'];end=m['end_l'];gap=4
            ix=bx+side;iy=by+end;iw=width-2*side;il=length-2*end
            corridors.extend([(ix-gap,iy-gap,iw+2*gap,gap),(ix-gap,iy+il,iw+2*gap,gap),(ix-gap,iy,gap,il),(ix+iw,iy,gap,il)])
            wings.extend([(bx,by,width,end-gap),(bx,by+length-end+gap,width,end-gap),(bx,by+end,side-gap,length-2*end),(bx+width-side+gap,by+end,side-gap,length-2*end)])
        return wings, corridors

    def _candidate(self,spec,width,length,side,units,strategy,sort_variant,shape,entry_variant=0):
        plot_polygon=[(x*3.280839895,y*3.280839895) for x,y in spec.plot_polygon] if spec.plot_polygon and spec.unit=='meters' else spec.plot_polygon
        setbacks=spec.setbacks.model_copy(deep=True)
        if spec.unit=='meters':
            for name in ('front_setback','rear_setback','left_setback','right_setback'):
                setattr(setbacks,name,getattr(setbacks,name)*3.280839895)
        footprint = generate_footprint(shape, width, length, spec.shape_parameters, setbacks, plot_polygon)
        m = footprint.metrics
        bx, by, maxx, maxy = footprint.bounding_box
        bw, bl = m['W'], m['L']
        rooms = []
        stairs = []
        floor_wings=[]
        floor_corridors=[]
        reserved_core=None
        for _ in range(spec.floors):
            wings,corridors=self.get_wings_and_corridors(shape,m,bx,by,bw,bl)
            if spec.floors>1 and shape==HouseShape.RECTANGLE:
                # Reserve the core before allocating rooms, beside the hall.
                # A four-foot hallway cannot double as a return stairwell.
                wx,wy,ww,wl=wings[0]
                if ww<8 or wl<32:
                    raise InfeasibleLayout('A separate return stair and landing require an 8 ft wide wing and 32 ft depth.')
                core_width=min(10,ww)
                if spec.road_location=='south':
                    reserved_core=(wx+ww-core_width,wy,core_width,12,'north')
                    wings[0]=(wx,wy+16,ww,wl-16)
                else:
                    reserved_core=(wx+ww-core_width,wy+wl-12,core_width,12,'south')
                    wings[0]=(wx,wy,ww,wl-16)
            floor_wings.append(wings);floor_corridors.append(corridors)

        # Assign every room exactly once, honoring explicit hard floor requirements and functional zone preferences
        floor_units=[[] for _ in range(spec.floors)]
        floor_load=[0.0 for _ in range(spec.floors)]
        floor_capacity=[sum(w[2]*w[3] for w in wings) for wings in floor_wings]
        def floor_sort_key(u):
            has_explicit = u['floor'] is not None
            cat = u.get('category', default_room_category(u['type']))
            cat_rank = 0 if cat in (RoomCategory.PUBLIC, RoomCategory.SERVICE) else 1
            return (not has_explicit, cat_rank, -u['minimum'], u['id'])
        ordered=sorted(units,key=floor_sort_key)
        for u in ordered:
            if u['floor'] is not None:
                choices=[u['floor']]
            elif self.entry_sitout and entry_variant==0 and u['id']=='living-1':
                choices=[0]
            else:
                cat = u.get('category', default_room_category(u['type']))
                if cat in (RoomCategory.PUBLIC, RoomCategory.SERVICE):
                    choices=[0] + list(range(1, spec.floors))
                else:
                    choices=(list(range(1, spec.floors)) + [0]) if spec.floors > 1 else [0]
            area=u['minimum']+(u['bath']*max(8.0,side) if u['bath'] else 0)
            feasible=[f for f in choices if floor_load[f]+area<=floor_capacity[f]+1e-6]
            if not feasible: raise InfeasibleLayout(f"{u['name']} cannot fit on the requested floor within the {shape.value.replace('_',' ')} footprint.")
            chosen=min(feasible,key=lambda f:(choices.index(f), floor_load[f]/max(1,floor_capacity[f])))
            floor_units[chosen].append(u);floor_load[chosen]+=area
        
        for f in range(spec.floors):
            wings, corridors = floor_wings[f], floor_corridors[f]
            
            for i, (cx, cy, cw, cl) in enumerate(corridors):
                rooms.append(RoomGeometry(id=f'hall-{f}-{i}', name='Circulation', type='hall', floor=f, x=cx, y=cy, width=cw, height=cl))
            
            wing_loads = [0.0] * len(wings)
            wing_assignments = [[] for _ in wings]
            assigned = floor_units[f]
            
            # Sort assigned rooms to cluster related pairs together for backtracking
            def unit_placement_rank(u):
                cat = u.get('category', default_room_category(u['type']))
                if strategy == 'PRIVATE_REAR':
                    cat_val = {RoomCategory.PRIVATE: 0, RoomCategory.SERVICE: 1, RoomCategory.PUBLIC: 2}.get(cat, 3)
                elif strategy == 'SERVICE_CLUSTER':
                    cat_val = {RoomCategory.SERVICE: 0, RoomCategory.PUBLIC: 1, RoomCategory.PRIVATE: 2}.get(cat, 3)
                else:
                    cat_val = {RoomCategory.PUBLIC: 0, RoomCategory.SERVICE: 1, RoomCategory.PRIVATE: 2}.get(cat, 3)
                return (cat_val, -u['minimum'], u['id'])
                
            order = sorted(assigned, key=unit_placement_rank)
            if sort_variant == 1:
                order = sorted(assigned, key=lambda u: (unit_placement_rank(u)[0], u['minimum'], u['id']))
            
            def required_depth(unit,wing_index):
                ww=wings[wing_index][2]
                depth=max(MIN_SIDE.get(unit['type'],6),(unit.get('minimum') or 0)/ww)+unit['bath'] if unit.get('minimum') else unit['min_depth']
                return max(18,depth) if unit['type']=='parking' else depth
            def road_facing_wings():
                """Return wings on the plot side declared as the vehicle approach."""
                side=spec.road_location
                edge_values=[]
                for wx,wy,ww,wl in wings:
                    edge_values.append({'north':wy,'south':wy+wl,'west':wx,'east':wx+ww}[side])
                target=(min(edge_values) if side in ('north','west') else max(edge_values))
                return {
                    wi for wi,(wx,wy,ww,wl) in enumerate(wings)
                    if abs(edge_values[wi]-target)<1e-5
                    and (ww>=8 if side in ('north','south') else wl>=8)
                }
            parking_wings=road_facing_wings()

            def calculate_wing_option_score(unit, wi, remaining):
                score = remaining if sort_variant == 0 else -remaining
                u_cat = unit.get('category', default_room_category(unit['type']))
                
                dist = _wing_road_dist(wi, wings, spec.road_location)
                
                if strategy == 'PUBLIC_FRONT':
                    if u_cat == RoomCategory.PUBLIC: score += max(-100, min(100, 100 - dist))
                    if u_cat == RoomCategory.PRIVATE: score += max(-100, min(100, dist - 100))
                elif strategy == 'PRIVATE_REAR':
                    if u_cat == RoomCategory.PRIVATE: score += max(-100, min(100, dist))
                    if u_cat == RoomCategory.PUBLIC: score += max(-100, min(100, 100 - dist))
                elif strategy == 'SERVICE_CLUSTER':
                    pass
                elif strategy == 'PUBLIC_CENTRAL':
                    wing_centroid_x = wings[wi][0] + wings[wi][2]/2
                    wing_centroid_y = wings[wi][1] + wings[wi][3]/2
                    dx = wing_centroid_x - (bx + bw/2)
                    dy = wing_centroid_y - (by + bl/2)
                    dist_to_center = hypot(dx, dy)
                    if u_cat == RoomCategory.PUBLIC: score += max(-100, min(100, 100 - dist_to_center))
                
                # Check explicit relationship affinity with already placed units
                for w_idx, placed_units in enumerate(wing_assignments):
                    for placed in placed_units:
                        for rel in spec.relationships:
                            rel_type = str(rel.relation.value if hasattr(rel.relation, 'value') else rel.relation)
                            is_pair = (
                                (unit['name'].lower() in rel.source.lower() or unit['type'].lower() in rel.source.lower() or unit['id'].lower() in rel.source.lower()) and
                                (placed['name'].lower() in rel.target.lower() or placed['type'].lower() in rel.target.lower() or placed['id'].lower() in rel.target.lower())
                            ) or (
                                (placed['name'].lower() in rel.source.lower() or placed['type'].lower() in rel.source.lower() or placed['id'].lower() in rel.source.lower()) and
                                (unit['name'].lower() in rel.target.lower() or unit['type'].lower() in rel.target.lower() or unit['id'].lower() in rel.target.lower())
                            )
                            if is_pair:
                                if rel_type in ('open_to', 'attached', 'connected', 'adjacent'):
                                    if wi == w_idx:
                                        score += 1000.0
                                elif rel_type in ('away_from', 'separated', 'must_not_be_adjacent'):
                                    if wi != w_idx:
                                        score += 500.0
                                    else:
                                        score -= 500.0
                
                # Zone coherence check
                placed_cats = [p.get('category', default_room_category(p['type'])) for p in wing_assignments[wi]]
                if placed_cats:
                    if u_cat in placed_cats:
                        score += 200.0
                    if u_cat == RoomCategory.PUBLIC and RoomCategory.PRIVATE in placed_cats:
                        score -= 300.0
                    if u_cat == RoomCategory.PRIVATE and RoomCategory.PUBLIC in placed_cats:
                        score -= 300.0
                return score

            def place(index):
                if index==len(order): return True
                unit=order[index];options=[]
                for wi,(_,_,ww,wl) in enumerate(wings):
                    if unit['type']=='parking' and wi not in parking_wings: continue
                    if self.entry_sitout and entry_variant==0 and f==0 and unit['id']=='living-1' and wi not in parking_wings: continue
                    if self.entry_sitout and entry_variant==0 and f==0:
                        # Vehicle and pedestrian rooms each need their own
                        # frontage; stacking them blocks one of the entries.
                        if unit['id']=='living-1' and any(p['type']=='parking' for p in wing_assignments[wi]):continue
                        if unit['type']=='parking' and any(p['id']=='living-1' for p in wing_assignments[wi]):continue
                    if ww<MIN_SIDE.get(unit['type'],3) or wl<=0: continue
                    depth=required_depth(unit,wi);remaining=wl-wing_loads[wi]-depth
                    if remaining>=-1e-6:
                        opt_score = calculate_wing_option_score(unit, wi, remaining)
                        options.append((opt_score,wi,depth))
                options.sort(key=lambda item: -item[0])
                for _,wi,depth in options:
                    wing_loads[wi]+=depth;wing_assignments[wi].append(unit)
                    if place(index+1): return True
                    wing_assignments[wi].pop();wing_loads[wi]-=depth
                return False
            if not place(0):
                raise InfeasibleLayout(f'No set of footprint-wing partitions can fit every room on floor {f+1}.')
                
            for i, (wx, wy, ww, wl) in enumerate(wings):
                group = wing_assignments[i]
                if not group: continue
                parking_rank=-1 if spec.road_location=='north' else 7
                def in_wing_sort_key(u):
                    if u['type'] in ('balcony','veranda','porch'): return (2 if reserved_core and self.entry_sitout and f==0 else -1, u['id'])
                    if u['type'] == 'parking': return (parking_rank, u['id'])
                    if self.entry_sitout and entry_variant==0 and f==0 and u['type']=='living': return (0, u['id'])
                    u_cat = u.get('category', default_room_category(u['type']))
                    cat_order = {RoomCategory.PUBLIC: 1, RoomCategory.SERVICE: 2, RoomCategory.PRIVATE: 3, RoomCategory.CIRCULATION: 4}.get(u_cat, 2)
                    return (cat_order, u['id'])
                group.sort(key=in_wing_sort_key, reverse=(sort_variant == 1))
                base_depths = [required_depth(u,i) for u in group]
                base_total = sum(base_depths)
                if base_total>wl+1e-6: raise InfeasibleLayout('Rooms exceed an available footprint wing.')
                extra = max(0, wl - base_total)
                flexible = [u for u in group if not u.get('exact')]
                weights = sum(u['depth'] for u in flexible) if flexible else 1
                
                y = wy
                corridor_at_end=any(abs((wy+wl)-cy)<1e-5 and max(wx,cx)<min(wx+ww,cx+cw)-1e-5 for cx,cy,cw,cl in corridors)
                for j, u in enumerate(group):
                    depth = base_depths[j] + (extra * u['depth'] / weights if not u.get('exact') and flexible else 0)
                    main_depth = max(0.1, depth - u['bath'])
                    main_y=y+(u['bath'] if corridor_at_end else 0)
                    bath_y=y if corridor_at_end else y+main_depth
                    rooms.append(RoomGeometry(id=u['id'], name=u['name'], type=u['type'], floor=f, x=wx, y=main_y, width=ww, height=main_depth, minimum_area=u.get('minimum')))
                    if u['bath']:
                        rooms.append(RoomGeometry(id=u['id']+'-bath', name=u['name']+' bath', type='bathroom', floor=f, x=wx, y=bath_y, width=ww, height=u['bath'], attached_to=u['id'], minimum_area=35))
                    y += depth

        core_open_pairs=set()
        if reserved_core:
            sx,sy,sw,sl,direction=reserved_core
            for f in range(spec.floors):
                rooms.append(RoomGeometry(id=f'stair-{f}',name='Enclosed return stair',type='stair',floor=f,x=sx,y=sy,width=sw,height=sl))
                rooms.append(RoomGeometry(id=f'landing-{f}',name='Stair landing',type='hall',floor=f,x=sx,y=sy-4 if direction=='south' else sy+sl,width=sw,height=4))
                core_open_pairs.add(tuple(sorted((f'landing-{f}',f'stair-{f}'))))
                if f<spec.floors-1:
                    stairs.append(Stair(id=f'stairs-{f}',from_floor=f,to_floor=f+1,x=sx,y=sy,width=sw,length=sl,direction=direction,kind='dogleg',landing_depth=4,risers=18))
        elif spec.floors > 1:
            # Reserve one aligned stair footprint across all storeys. A stair
            # occupying the full corridor width must be at a terminal end,
            # never in its middle where it would sever through-circulation.
            corridor_index = 2 if shape == HouseShape.COURTYARD else 1 if shape == HouseShape.U_SHAPE else 0
            cx, cy, cw, cl = floor_corridors[0][corridor_index]
            if cw < 3.5 or cl < 12:
                raise InfeasibleLayout('The circulation corridor cannot fit a 4 × 12 ft staircase.')
            options = [(cx, cy, cw, 12), (cx, cy + cl - 12, cw, 12)]

            def stair_cost(rect):
                sx, sy, sw, sl = rect
                zone = box(sx, sy, sx + sw, sy + sl)
                # The approach is the open end of the stair, not the centre
                # of the steps. Prefer an approach near the public entry and
                # living space, while avoiding bedroom doors opening onto steps.
                approach_y = sy + sl if abs(sy - cy) < 1e-5 else sy
                approach_x = sx + sw / 2
                cost = 0.0
                if spec.road_location == 'north':
                    cost += 4 * abs(approach_y)
                elif spec.road_location == 'south':
                    cost += 4 * abs(length - approach_y)
                for room in rooms:
                    if room.floor != 0 or room.type not in ('porch', 'living', 'dining'):
                        continue
                    weight = {'porch': 3, 'living': 2, 'dining': 1}[room.type]
                    cost += weight * bounds(room).distance(box(approach_x, approach_y,
                                                               approach_x + .01, approach_y + .01))
                for room in rooms:
                    if room.type in ('hall', 'stair'):
                        continue
                    if bounds(room).boundary.intersection(zone.boundary).length > 2.9:
                        cost += 12 if room.type in ('bedroom', 'bathroom') else 3
                return cost

            sx, sy, sw, sl = min(options, key=stair_cost)
            for f in range(spec.floors):
                rooms.append(RoomGeometry(id=f'stair-{f}', name='Staircase', type='stair',
                                          floor=f, x=sx, y=sy, width=sw, height=sl))
                if f < spec.floors - 1:
                    stairs.append(Stair(id=f'stairs-{f}', from_floor=f, to_floor=f+1,
                                        x=sx, y=sy, width=sw, length=sl))

        plot_boundary=plot_polygon or [(0,0),(width,0),(width,length),(0,length)]
        layout = HouseLayout(width=width, length=length, floors=spec.floors, footprint=footprint, plot_boundary=plot_boundary, setback_boundary=footprint.buildable_boundary or [], road_edge=road_edge(spec.road_location,width,length), strategy=strategy, rooms=rooms, walls=[], doors=[], windows=[], stairs=stairs)
        build_walls(layout, spec,extra_open_pairs=core_open_pairs)
        build_openings(layout, spec)
        if spec.spatial_intent:
            for constraint in spec.spatial_intent.constraints:
                if constraint.kind == 'relationship' and constraint.priority == 'hard' and constraint.room and constraint.target:
                    rel = Relationship(
                        source=constraint.room.name or constraint.room.type,
                        target=constraint.target.name or constraint.target.type,
                        relation=constraint.relation
                    )
                    if not relationship_ok(layout, rel):
                        raise InfeasibleLayout(f"Hard architectural relationship '{constraint.source_text}' could not be satisfied.")
        return layout

def get_open_to_pairs(spec, layout):
    """Returns set of normalized room ID tuples (room_id_1, room_id_2) with open_to relationship."""
    if not spec:
        return set()
    open_pairs = set()
    rels = []
    if spec.relationships:
        rels.extend(spec.relationships)
    if getattr(spec, 'spatial_intent', None) and spec.spatial_intent and spec.spatial_intent.constraints:
        for constraint in spec.spatial_intent.constraints:
            if constraint.kind == 'relationship' and constraint.room and constraint.target:
                rels.append(Relationship(
                    source=constraint.room.name or constraint.room.type,
                    target=constraint.target.name or constraint.target.type,
                    relation=constraint.relation
                ))
    if getattr(spec, 'architectural_layout_intent', None) and spec.architectural_layout_intent:
        for rrel in spec.architectural_layout_intent.architectural_relationships:
            rels.append(Relationship(
                source=rrel.source.name or rrel.source.type,
                target=rrel.target.name or rrel.target.type,
                relation=rrel.relation
            ))
    if getattr(spec, 'preferences', None) and spec.preferences.get('open_kitchen'):
        rels.append(Relationship(source='dining', target='kitchen', relation='open_to'))
        rels.append(Relationship(source='living', target='kitchen', relation='open_to'))

    for rel in rels:
        rel_str = str(rel.relation.value if hasattr(rel.relation, 'value') else rel.relation).lower()
        if rel_str == 'open_to':
            sources = match_rooms(layout, rel.source)
            targets = match_rooms(layout, rel.target)
            for s in sources:
                for t in targets:
                    if s.id != t.id and s.floor == t.floor:
                        open_pairs.add(tuple(sorted([s.id, t.id])))
                        
    # Implicit Open Concepts: automatically suppress walls between standard public zones
    open_types = {'kitchen', 'dining', 'living'}
    for r1 in layout.rooms:
        for r2 in layout.rooms:
            if r1.id != r2.id and r1.floor == r2.floor:
                if r1.type in open_types and r2.type in open_types:
                    if spec.preferences.get('open_kitchen') is False and 'kitchen' in (r1.type,r2.type):continue
                    open_pairs.add(tuple(sorted([r1.id, r2.id])))

    # Stair edges are not emitted by build_walls. Suppressing a coincident
    # hall edge here could also erase a required living-to-hall door wall.
    return open_pairs

def build_walls(layout, spec=None, extra_open_pairs=None):
    # Rebuilding walls (for example after carving an entry porch) must retain
    # the open boundary between a return stair and its level landing.
    from .stair_geometry import entry_edge
    extra_open_pairs=set(extra_open_pairs or ())
    for s in layout.stairs:
        if s.kind!='dogleg':continue
        edge=entry_edge(s)
        for f in (s.from_floor,s.to_floor):
            core=next((r for r in layout.rooms if r.id==f'stair-{f}'),None)
            if core:
                for h in layout.rooms:
                    if h.floor==f and h.type=='hall' and bounds(h).boundary.intersection(edge).length>=edge.length-.01:
                        extra_open_pairs.add(tuple(sorted((core.id,h.id))))
    # Split collinear edges at every junction, then deduplicate shared walls.
    floor_shapes = defaultdict(list)
    for r in layout.rooms:
        floor_shapes[r.floor].append(bounds(r))
    floor_boundaries = {f: unary_union(shapes).boundary for f, shapes in floor_shapes.items()}
    
    raw=[]
    for r in layout.rooms:
        if r.type == 'stair' and layout.strategy != 'MODERN_DUPLEX' and not any(s.kind=='dogleg' for s in layout.stairs):
            # Skip generating standalone wall segments for the staircase itself.
            # Since it is embedded inside the hall, the hall's boundaries will
            # provide the exterior enclosure, leaving the entrance perfectly open.
            continue
            
        points=r.polygon
        for a,b in zip(points,points[1:]+points[:1]):
            if abs(a[1]-b[1])<1e-6: raw.append((r.floor,'h',a[1],min(a[0],b[0]),max(a[0],b[0])))
            elif abs(a[0]-b[0])<1e-6: raw.append((r.floor,'v',a[0],min(a[1],b[1]),max(a[1],b[1])))
            else: raise InfeasibleLayout(f'Room {r.name} contains a non-orthogonal wall; the current wall builder supports orthogonal polygons.')
    groups=defaultdict(list)
    for f,axis,fixed,a,b in raw: groups[(f,axis,round(fixed,6))].append((a,b))
    
    walls = []
    for (f,axis,fixed),segments in groups.items():
        points=sorted(set(round(v,6) for seg in segments for v in seg))
        for a,b in zip(points,points[1:]):
            if b-a<0.001 or not any(lo-1e-5<=(a+b)/2<=hi+1e-5 for lo,hi in segments): continue
            w_line = LineString([(a if axis=='h' else fixed, fixed if axis=='h' else a), (b if axis=='h' else fixed, fixed if axis=='h' else b)])
            exterior = floor_boundaries[f].buffer(1e-5).covers(w_line)
            walls.append(Wall(id=f'wall-{len(walls)}',floor=f,x1=a if axis=='h' else fixed,y1=fixed if axis=='h' else a,x2=b if axis=='h' else fixed,y2=fixed if axis=='h' else b,exterior=exterior))

    # Perform physical open_to wall suppression if spec is provided
    if spec or extra_open_pairs:
        open_pairs = get_open_to_pairs(spec, layout) | set(extra_open_pairs or ())
        rooms_by_id = {r.id: r for r in layout.rooms}
        suppressed_wall_ids = set()
        for pair in open_pairs:
            r1_id, r2_id = pair
            r1 = rooms_by_id.get(r1_id)
            r2 = rooms_by_id.get(r2_id)
            if not r1 or not r2 or r1.floor != r2.floor:
                continue
            b1_boundary = bounds(r1).boundary.buffer(1e-5)
            b2_boundary = bounds(r2).boundary.buffer(1e-5)
            for w in walls:
                if w.floor == r1.floor and not w.exterior:
                    w_line = wall_line(w)
                    if b1_boundary.covers(w_line) and b2_boundary.covers(w_line):
                        suppressed_wall_ids.add(w.id)
        walls = [w for w in walls if w.id not in suppressed_wall_ids]

    # Re-index wall IDs sequentially
    for idx, w in enumerate(walls):
        w.id = f'wall-{idx}'
    layout.walls = walls

def shared_wall(layout,a,b=None,exterior=False):
    shape=bounds(a).boundary
    return [w for w in layout.walls if w.floor==a.floor and wall_line(w).length>=2.9 and shape.buffer(1e-5).covers(wall_line(w)) and (not exterior or w.exterior) and (b is None or bounds(b).boundary.buffer(1e-5).covers(wall_line(w)))]

def physically_open_pairs(layout):
    """Derive walkable open boundaries from geometry, without requiring an LLM label."""
    result=set()
    for index,a in enumerate(layout.rooms):
        for b in layout.rooms[index+1:]:
            if a.floor!=b.floor or a.type=='stair' or b.type=='stair': continue
            shared=bounds(a).boundary.intersection(bounds(b).boundary)
            if shared.length<2.9: continue
            blocked=sum(wall_line(w).intersection(shared).length for w in layout.walls if w.floor==a.floor)
            if shared.length-blocked>=2.9:
                result.add(tuple(sorted((a.id,b.id))))
    return result

def vehicle_path_clear(layout,parking,wall,road_side):
    """A vehicle must be able to travel straight from its gate to the declared road without crossing another room."""
    mx=(wall.x1+wall.x2)/2;my=(wall.y1+wall.y2)/2
    target={'south':(mx,layout.length),'north':(mx,0),'west':(0,my),'east':(layout.width,my)}[road_side]
    path=LineString([(mx,my),target])
    # When the gate itself lies on the road-facing plot boundary, no separate
    # driveway segment is needed: the vehicle enters directly through it.
    if path.length<=0.05:
        return True
    obstacles=[bounds(r) for r in layout.rooms if r.floor==0 and r.id!=parking.id]
    blocked=unary_union(obstacles).buffer(-0.05).intersects(path) if obstacles else False
    return not blocked

def vehicle_gate_wall(layout,parking,road_side):
    candidates=[]
    for wall in shared_wall(layout,parking,exterior=True):
        length=wall_line(wall).length
        horizontal=abs(wall.y2-wall.y1)<1e-6
        aligned=horizontal if road_side in ('north','south') else not horizontal
        if length<8 or not aligned or not vehicle_path_clear(layout,parking,wall,road_side): continue
        mx=(wall.x1+wall.x2)/2;my=(wall.y1+wall.y2)/2
        distance={'south':layout.length-my,'north':my,'west':mx,'east':layout.width-mx}[road_side]
        candidates.append((distance,-length,wall))
    return min(candidates,key=lambda item:(item[0],item[1]))[2] if candidates else None

def carve_entry_sitout(layout,spec):
    """Recess a road-facing ground-floor living room into a real entry space.

    This is used only by the application-facing generator. The legacy engine's
    direct baseline mode remains unchanged. If geometry cannot accommodate a
    sit-out, the candidate is rejected instead of accepting a room-direct door.
    """
    side = spec.road_location
    requested=next((r for r in spec.rooms if r.type=='porch' and r.preferred_floor in (None,0)),None)
    scale=3.280839895 if spec.unit=='meters' else 1
    sitout_area=max(50,(requested.minimum_area or 0)*scale**2 if requested else 0)
    ground = [r for r in layout.rooms if r.floor == 0 and r.type != 'stair']
    living_rooms = [r for r in ground if r.type == 'living']
    if not living_rooms:
        raise InfeasibleLayout('An entry sit-out needs a ground-floor living room.')
    front = {'north': min(r.y for r in ground),
             'south': max(r.y+r.height for r in ground),
             'west': min(r.x for r in ground),
             'east': max(r.x+r.width for r in ground)}[side]
    exact_living = [r for r in spec.rooms if r.type == 'living' and (r.exact_width or r.exact_length)]
    if exact_living:
        raise InfeasibleLayout('An exact living-room dimension leaves no verified space for the required sit-out.')
    for living in living_rooms:
        extent = {'north': living.y, 'south': living.y+living.height,
                  'west': living.x, 'east': living.x+living.width}[side]
        if abs(extent-front) > .01:
            continue
        frontage = living.width if side in ('north','south') else living.height
        if frontage < 7:
            continue
        depth = max(5.0, sitout_area/frontage)
        remaining = (living.height if side in ('north','south') else living.width)-depth
        new_area = frontage*remaining
        if remaining < MIN_SIDE['living'] or new_area+.01 < max(MIN_AREA['living'],living.minimum_area):
            continue
        x,y,w,h = living.x,living.y,living.width,living.height
        if side == 'north':
            porch_rect=(x,y,w,depth); living.y=y+depth; living.height=h-depth
        elif side == 'south':
            porch_rect=(x,y+h-depth,w,depth); living.height=h-depth
        elif side == 'west':
            porch_rect=(x,y,depth,h); living.x=x+depth; living.width=w-depth
        else:
            porch_rect=(x+w-depth,y,depth,h); living.width=w-depth
        living.polygon=[(living.x,living.y),(living.x+living.width,living.y),
                        (living.x+living.width,living.y+living.height),(living.x,living.y+living.height)]
        px,py,pw,ph=porch_rect
        porch=RoomGeometry(id='porch-1',name=requested.name if requested else 'Entrance sit-out',type='porch',floor=0,
                           x=px,y=py,width=pw,height=ph,minimum_area=sitout_area)
        layout.rooms.append(porch)
        layout.walls=[];layout.doors=[];layout.windows=[]
        build_walls(layout,spec)
        build_openings(layout,spec)
        if not any(d.room_a==porch.id and d.room_b==living.id for d in layout.doors):
            raise InfeasibleLayout('The sit-out does not connect directly to the living room.')
        return layout
    raise InfeasibleLayout('No road-facing living room has enough space for a 50 sq ft entry sit-out.')

def road_facing_wall(wall,room,side):
    if side == 'north': return abs(wall.y1-room.y)<.001 and abs(wall.y2-room.y)<.001
    if side == 'south': return abs(wall.y1-(room.y+room.height))<.001 and abs(wall.y2-(room.y+room.height))<.001
    if side == 'west': return abs(wall.x1-room.x)<.001 and abs(wall.x2-room.x)<.001
    return abs(wall.x1-(room.x+room.width))<.001 and abs(wall.x2-(room.x+room.width))<.001

def build_openings(layout,spec):
    by_id={r.id:r for r in layout.rooms}
    has_sitout=any(r.type=='porch' and r.floor==0 for r in layout.rooms)
    for r in layout.rooms:
        if r.type=='hall':
            if r.floor==0 and not has_sitout:
                ws=shared_wall(layout,r,exterior=True)
                if ws: add_door(layout,r,None,ws[-1])
            continue
        if r.type=='porch' and r.floor==0:
            living=next((candidate for candidate in layout.rooms
                         if candidate.type=='living' and candidate.floor==0
                         and shared_wall(layout,r,candidate)),None)
            if not living:
                raise InfeasibleLayout('The entry sit-out is not adjacent to a ground-floor living room.')
            wall=max(shared_wall(layout,r,living),key=lambda item:wall_line(item).length)
            add_door(layout,r,living,wall,width=min(3.2,wall_line(wall).length-.4))
            front=[w for w in shared_wall(layout,r,exterior=True)
                   if road_facing_wall(w,r,spec.road_location)]
            if not front:
                raise InfeasibleLayout('The entry sit-out has no road-facing exterior opening.')
            add_door(layout,r,None,max(front,key=lambda item:wall_line(item).length),width=3.2)
            continue
        if r.type=='stair':
            # Stairs are embedded in circulation geometry; accessibility is
            # represented by the semantic Stair connection, not a swing door.
            continue
        ws = []
        target = None
        if r.attached_to:
            target = by_id.get(r.attached_to)
            if target: ws = shared_wall(layout, r, target)
        else:
            for h in layout.rooms:
                if h.type == 'hall' and h.floor == r.floor:
                    alt_ws = shared_wall(layout, r, h)
                    if alt_ws:
                        target = h; ws = alt_ws; break
            if not ws and r.type != 'stair' and layout.floors > 1:
                target = by_id.get(f'stair-{r.floor}')
                if target: ws = shared_wall(layout, r, target)
            if not ws and r.type != 'stair':
                others=sorted(layout.rooms,key=lambda other:(r.type=='bathroom' and other.type=='kitchen',other.type in ('bathroom','parking'),other.id))
                for other in others:
                    if other.id != r.id and other.floor == r.floor:
                        alt_ws = shared_wall(layout, r, other)
                        if alt_ws:
                            target = other; ws = alt_ws; break
        if ws and target and not (has_sitout and r.type=='parking'):
            add_door(layout,r,target,max(ws,key=lambda w:wall_line(w).length))
        if r.type=='parking':
            gate_wall=vehicle_gate_wall(layout,r,spec.road_location)
            if gate_wall:
                gate_width=min(9.0,wall_line(gate_wall).length)
                layout.windows=[window for window in layout.windows if window.wall!=gate_wall.id]
                add_door(layout,r,None,gate_wall,width=gate_width,kind='vehicle')
            continue
        if r.type not in ('stair','parking'):
            ws=shared_wall(layout,r,exterior=True)
            if ws:
                w=max(ws,key=lambda w:wall_line(w).length);size=min(4,wall_line(w).length-1)
                layout.windows.append(Window(id='window-'+r.id,room=r.id,wall=w.id,position=(wall_line(w).length-size)/2,width=size))
    if not any(d.room_b is None and d.kind not in ('vehicle','courtyard') for d in layout.doors):
        entry_candidates=sorted((r for r in layout.rooms if r.floor==0 and r.type not in ('hall','stair','bathroom')),key=lambda r:(r.type!='living',r.type!='parking',r.id))
        for entry in entry_candidates:
            ws=shared_wall(layout,entry,exterior=True)
            if ws:
                wall=max(ws,key=lambda w:wall_line(w).length)
                layout.windows=[w for w in layout.windows if w.wall!=wall.id]
                add_door(layout,entry,None,wall)
                break
    halls=[r for r in layout.rooms if r.type=='hall']
    for index,a in enumerate(halls):
        for b in halls[index+1:]:
            if a.floor!=b.floor: continue
            ws=shared_wall(layout,a,b)
            if ws and not any({d.room_a,d.room_b}=={a.id,b.id} for d in layout.doors):
                add_door(layout,a,b,max(ws,key=lambda w:wall_line(w).length))
    for rel in spec.relationships:
        if rel.relation not in ('connected','attached','accessible_from'): continue
        aa=match_rooms(layout,rel.source);bb=match_rooms(layout,rel.target)
        for a in aa:
            for b in bb:
                if a.floor==b.floor:
                    ws=shared_wall(layout,a,b)
                    if ws and not any(d.wall==ws[0].id for d in layout.doors): add_door(layout,a,b,ws[0])

    # ── Room Accessibility Fallback ──────────────────────────────────────
    # After all doors are placed, check reachability via BFS from exterior
    # doors. Any room that is still unreachable gets a forced door onto its
    # longest shared wall with ANY adjacent room (relaxed 2.0 ft minimum).
    rooms_by_id = {r.id: r for r in layout.rooms}
    adj = defaultdict(set)
    ext_ids = []
    for d in layout.doors:
        if d.room_b:
            adj[d.room_a].add(d.room_b); adj[d.room_b].add(d.room_a)
        else:
            ext_ids.append(d.room_a)
    # Include open-concept accessibility
    for pair in get_open_to_pairs(spec, layout):
        r1_id, r2_id = pair
        r1 = rooms_by_id.get(r1_id); r2 = rooms_by_id.get(r2_id)
        if r1 and r2 and r1.floor == r2.floor:
            if bounds(r1).boundary.intersection(bounds(r2).boundary).length > 0.1:
                adj[r1.id].add(r2.id); adj[r2.id].add(r1.id)
    # Include stair connectivity
    for s in layout.stairs:
        a = rooms_by_id.get(f'stair-{s.from_floor}'); b = rooms_by_id.get(f'stair-{s.to_floor}')
        if a and b: adj[a.id].add(b.id); adj[b.id].add(a.id)
        for room in layout.rooms:
            if room.type == 'hall' and room.floor in (s.from_floor, s.to_floor):
                sr = rooms_by_id.get(f'stair-{room.floor}')
                if sr and bounds(sr).intersects(bounds(room)):
                    adj[sr.id].add(room.id); adj[room.id].add(sr.id)
    # BFS from exterior
    seen = set(ext_ids); todo = list(ext_ids)
    while todo:
        for n in adj[todo.pop()] - seen: seen.add(n); todo.append(n)
    # Force doors for unreachable rooms
    for r in layout.rooms:
        if r.id in seen or r.type == 'stair':
            continue
        # Find any adjacent room that IS reachable, try to place a door
        best_wall = None; best_target = None; best_len = 0
        for other in layout.rooms:
            if other.id == r.id or other.floor != r.floor: continue
            # Relaxed minimum: check walls >= 2.0 ft instead of 2.9 ft
            shape = bounds(r).boundary
            for w in layout.walls:
                if w.floor != r.floor: continue
                wl = wall_line(w)
                if wl.length < 2.0: continue
                if not shape.buffer(1e-5).covers(wl): continue
                if not bounds(other).boundary.buffer(1e-5).covers(wl): continue
                if w.exterior: continue  # Don't put interior doors on exterior walls
                if wl.length > best_len:
                    best_wall = w; best_target = other; best_len = wl.length
        if best_wall and best_target:
            add_door(layout, r, best_target, best_wall, width=min(2.6, best_len - 0.3))
            # Update adjacency and re-check reachability
            adj[r.id].add(best_target.id); adj[best_target.id].add(r.id)
            if best_target.id in seen:
                seen.add(r.id); todo2 = [r.id]
                while todo2:
                    for n in adj[todo2.pop()] - seen: seen.add(n); todo2.append(n)

def add_door(layout,a,b,w,width=2.6,kind=None):
    kind=kind or ('entry' if b is None else 'interior')
    layout.doors.append(Door(id=f'door-{len(layout.doors)}',room_a=a.id,room_b=b.id if b else None,wall=w.id,position=(wall_line(w).length-width)/2,width=width,kind=kind))

def match_rooms(layout,name):
    return [r for r in layout.rooms if name.lower() in (r.type.lower(),r.name.lower(),r.id.lower())]

def relationship_ok(layout,rel):
    pairs=[(a,b) for a in match_rooms(layout,rel.source) for b in match_rooms(layout,rel.target) if a.id!=b.id]
    def check(a,b):
        shared_length = bounds(a).boundary.intersection(bounds(b).boundary).length if a.floor==b.floor else 0.0
        adjacent = a.floor==b.floor and shared_length>0.1
        r = str(rel.relation.value if hasattr(rel.relation,'value') else rel.relation)
        if r in ('connected','attached','accessible_from','accessed_from'):
            return any({d.room_a,d.room_b}=={a.id,b.id} for d in layout.doors) or adjacent
        if r in ('must_not_be_adjacent','separated','away_from'):
            if r == 'away_from':
                return a.floor!=b.floor or bounds(a).distance(bounds(b))>=10.0
            return not adjacent
        if r in ('open_to','adjacent'):
            return adjacent
        if r in ('near','preferred_near'):
            return a.floor==b.floor and bounds(a).distance(bounds(b))<12.0
        return adjacent
    rel_kind = str(rel.relation.value if hasattr(rel.relation,'value') else rel.relation)
    return bool(pairs) and (all(check(a,b) for a,b in pairs) if rel_kind in ('must_not_be_adjacent','separated') else any(check(a,b) for a,b in pairs))

def validate(layout,spec):
    checks=[]
    def result(name,ok,detail='',warning=False): checks.append(Check(name=name,status='PASS' if ok else ('WARNING' if warning else 'ERROR'),detail=detail))
    plot=Polygon(layout.plot_boundary) if layout.plot_boundary else box(0,0,layout.width,layout.length)
    footprint=footprint_polygon(layout.footprint) if layout.footprint else plot
    result('Valid building polygon',footprint.is_valid and footprint.area>0,validate_footprint(layout.footprint,layout.plot_boundary if spec.plot_polygon else None)[0] if layout.footprint and validate_footprint(layout.footprint,layout.plot_boundary if spec.plot_polygon else None) else 'GEOS topology is valid.')
    result('Building inside plot',plot.buffer(1e-5).covers(footprint))
    setback=Polygon(layout.setback_boundary) if layout.setback_boundary else plot
    result('Setbacks respected',setback.buffer(1e-5).covers(footprint))
    result('All rooms inside selected footprint',all(footprint.buffer(1e-5).covers(bounds(r)) for r in layout.rooms))
    result('No room overlaps',all(a.floor!=b.floor  or bounds(a).intersection(bounds(b)).area<1e-5 for i,a in enumerate(layout.rooms) for b in layout.rooms[i+1:]))
    result('Valid floor assignments',all(0<=r.floor<layout.floors for r in layout.rooms))
    result('Minimum room sizes',all(r.width*r.height+0.01>=r.minimum_area and min(r.width,r.height)+0.01>=MIN_SIDE.get(r.type,0) for r in layout.rooms))
    counts=Counter(r.type for r in layout.rooms if not r.attached_to)
    for kind in set(r.type for r in spec.rooms):
        n=sum(r.count for r in spec.rooms if r.type==kind)
        result(f'{n} {kind}'+('s' if n!=1 else ''),counts[kind]>=n,f'{counts[kind]} generated')
    floor_requests=Counter()
    for request in spec.rooms:
        if request.preferred_floor is not None:floor_requests[(request.type,request.preferred_floor)]+=request.count
    for (kind,floor),needed in floor_requests.items():
        actual=sum(r.type==kind and r.floor==floor and not r.attached_to for r in layout.rooms)
        label='Ground floor' if floor==0 else f'Floor {floor+1}'
        result(f'{label}: {needed} {kind}',actual>=needed,f'{actual} generated on the requested floor.')
    attached=sum(r.count for r in spec.rooms if r.attached_bathroom)
    result(f'{attached} attached bathrooms',sum(bool(r.attached_to) for r in layout.rooms)>=attached)
    result(f'{spec.parking_spaces} parking spaces',counts['parking']>=spec.parking_spaces)
    walls={w.id:w for w in layout.walls};rooms={r.id:r for r in layout.rooms}
    valid_doors=True
    adjacency=defaultdict(set)
    exterior=[]
    for d in layout.doors:
        w=walls.get(d.wall);a=rooms.get(d.room_a);b=rooms.get(d.room_b)
        if not w or not a or (d.room_b and not b): valid_doors=False;continue
        length=wall_line(w).length
        valid_doors &= d.position>=0 and d.position+d.width<=length+1e-5 and w.floor==a.floor and bounds(a).boundary.buffer(1e-5).covers(wall_line(w))
        if d.kind=='vehicle':
            valid_doors &= a.type=='parking' and b is None and w.exterior and d.width>=8
        if b:
            valid_doors &= a.floor==b.floor and bounds(b).boundary.buffer(1e-5).covers(wall_line(w))
            adjacency[a.id].add(b.id);adjacency[b.id].add(a.id)
        else:
            valid_doors &= w.exterior
            if d.kind=='courtyard':
                valid_doors &= bool(layout.footprint and layout.footprint.courtyard and Polygon(layout.footprint.courtyard).boundary.buffer(1e-5).covers(wall_line(w)))
            else:exterior.append(a.id)
    for i,a in enumerate(layout.doors):
        for b in layout.doors[i+1:]:
            if a.wall==b.wall and min(a.position+a.width,b.position+b.width)-max(a.position,b.position)>0: valid_doors=False
    result('Doors connect valid spaces',valid_doors)
    parking_rooms=[r for r in layout.rooms if r.type=='parking']
    vehicle_access=all(any(d.kind=='vehicle' and d.room_a==r.id and d.room_b is None and d.width>=8 and walls.get(d.wall) and vehicle_path_clear(layout,r,walls[d.wall],spec.road_location) for d in layout.doors) for r in parking_rooms)
    result('Parking has road-reachable vehicle access',vehicle_access,'Each vehicle bay requires an exterior gate at least 8 ft wide with an unobstructed route to the declared road edge.')
    valid_windows=True
    for win in layout.windows:
        w=walls.get(win.wall);r=rooms.get(win.room)
        valid_windows &= bool(w and r and w.exterior and w.floor==r.floor and win.position>=0 and win.position+win.width<=wall_line(w).length+1e-5 and bounds(r).boundary.buffer(1e-5).covers(wall_line(w)))
        for d in layout.doors:
            if d.wall==win.wall and min(d.position+d.width,win.position+win.width)>max(d.position,win.position): valid_windows=False
    result('Windows on exterior walls',valid_windows)
    stair_ok=len(layout.stairs)==layout.floors-1
    for s in layout.stairs:
        a=rooms.get(f'stair-{s.from_floor}');b=rooms.get(f'stair-{s.to_floor}')
        stair_ok &= bool(a and b and s.to_floor==s.from_floor+1 and bounds(a).equals(bounds(b)))
        if a and b: adjacency[a.id].add(b.id);adjacency[b.id].add(a.id)
        # The stair footprint is intentionally embedded in the circulation zone.
        for room in layout.rooms:
            if room.type=='hall' and room.floor in (s.from_floor,s.to_floor):
                stair_room=rooms.get(f'stair-{room.floor}')
                if stair_room and bounds(stair_room).intersects(bounds(room)):
                    adjacency[stair_room.id].add(room.id);adjacency[room.id].add(stair_room.id)
    result('Staircase connects floors',stair_ok)
    from .stair_geometry import stair_checks
    checks.extend(stair_checks(layout))
    
    # Include open_to spatial accessibility (open physical boundary)
    open_pairs = get_open_to_pairs(spec, layout)
    if layout.strategy in ('SIMPLE_HOME', 'COURTYARD_HOME', 'MODERN_DUPLEX', 'SINGLE_COURTYARD'):
        open_pairs |= physically_open_pairs(layout)
    for pair in open_pairs:
        r1_id, r2_id = pair
        r1 = rooms.get(r1_id)
        r2 = rooms.get(r2_id)
        if r1 and r2 and r1.floor == r2.floor:
            if bounds(r1).boundary.intersection(bounds(r2).boundary).length > 0.1:
                adjacency[r1.id].add(r2.id)
                adjacency[r2.id].add(r1.id)

    seen=set(exterior);todo=list(exterior)
    while todo:
        for n in adjacency[todo.pop()]-seen: seen.add(n);todo.append(n)
    result('All rooms accessible',all(r.id in seen for r in layout.rooms))
    result('Road access available',bool(exterior),'An exterior entrance connects the circulation graph.')
    bathroom_kitchen=any({rooms.get(d.room_a).type if rooms.get(d.room_a) else '',rooms.get(d.room_b).type if d.room_b and rooms.get(d.room_b) else ''}=={'bathroom','kitchen'} for d in layout.doors)
    result('Bathrooms avoid direct kitchen access',not bathroom_kitchen)
    entrance_rooms=[rooms[rid] for rid in exterior if rid in rooms]
    result('Entrance serves public space',any(r.type in ('hall','living','parking','porch') for r in entrance_rooms),'Exterior entry should lead to circulation, living, or an entry porch.',warning=True)
    sitouts=[r for r in layout.rooms if r.id=='porch-1' and r.type=='porch' and r.floor==0]
    if layout.strategy in ('SIMPLE_HOME','COURTYARD_HOME','LEGACY_FALLBACK') or sitouts:
        pedestrian_entries=[d for d in layout.doors if d.room_b is None and d.kind not in ('vehicle','courtyard')]
        route_ok=(len(sitouts)==1 and bool(pedestrian_entries)
                  and all(d.room_a==sitouts[0].id for d in pedestrian_entries)
                  and any(d.room_a==sitouts[0].id and d.room_b and
                          rooms.get(d.room_b) and rooms[d.room_b].type=='living'
                          for d in layout.doors))
        result('Road to sit-out to living route',route_ok,
               'Every pedestrian entry must reach a distinct sit-out before the living room.')
        result('Sit-out has usable space',len(sitouts)==1 and
               bounds(sitouts[0]).area>=50 and min(sitouts[0].width,sitouts[0].height)>=4,
               'The sit-out requires at least 50 sq ft and a 4 ft clear side.')
        result('Sit-out faces the road',len(sitouts)==1 and all(
               walls.get(d.wall) and road_facing_wall(walls[d.wall],sitouts[0],spec.road_location)
               and vehicle_path_clear(layout,sitouts[0],walls[d.wall],spec.road_location)
               for d in pedestrian_entries if d.room_a==sitouts[0].id),
               'The front entry must have a clear approach from the declared road side.')
        result('Parking cannot bypass the sit-out',not any(
               d.room_b and rooms.get(d.room_a) and rooms[d.room_a].type=='parking'
               and rooms.get(d.room_b) and rooms[d.room_b].type!='porch'
               for d in layout.doors),
               'A car bay must not provide a shortcut into bedrooms, bathrooms or the living room.')
    if layout.strategy == 'COURTYARD_HOME':
        public = {kind: [r for r in layout.rooms if r.type == kind]
                  for kind in ('living', 'dining', 'kitchen')}
        public_ground = (sum(r.floor == 0 for r in public['living']) == 1
                         and all(len(public[kind]) == 1 and public[kind][0].floor == 0
                                 for kind in ('dining', 'kitchen')))
        pedestrian_entries = [d for d in layout.doors if d.room_b is None and d.kind not in ('vehicle','courtyard')]
        result('Public rooms stay on entrance floor', public_ground,
               'Living, dining and kitchen must share the ground floor.')
        result('Pedestrian arrival uses sit-out first', bool(pedestrian_entries) and
               all(rooms.get(d.room_a) and rooms[d.room_a].type == 'porch' for d in pedestrian_entries),
               'The front sit-out separates the road from living, dining and bathrooms.')
        result('Dining opens directly to kitchen', public_ground and
               tuple(sorted((public['dining'][0].id, public['kitchen'][0].id))) in physically_open_pairs(layout),
               'The dining–kitchen boundary is walkable without a wall or swing door.')
        result('Parking is separate from interior circulation',
               not any(d.room_b and rooms.get(d.room_a) and rooms[d.room_a].type == 'parking'
                       for d in layout.doors),
               'The car porch has road access but no shortcut into a private room.')
    for rel in spec.relationships:
        rel_name = rel.relation.replace("_"," ") if isinstance(rel.relation,str) else rel.relation.value.replace("_"," ")
        result(f'{rel.source} {rel_name} {rel.target}',relationship_ok(layout,rel),'Measured from generated room boundaries and door connections.',warning=rel.relation not in ('must_not_be_adjacent','attached'))
    for r in layout.rooms:
        if r.type in ('bedroom','living','kitchen') and not any(w.room==r.id for w in layout.windows): result(r.name+' daylight',False,'No exterior window generated.',True)
    if not any(r.type=='bathroom' for r in layout.rooms):
        result('Bathroom missing from brief',False,'No bathroom was requested or generated. Add a shared bathroom before treating this as a usable home plan.',True)
    for request in spec.special_requirements: result('Additional requirement',False,request+' — requires manual review; not enforced by the current engine.',True)
    if spec.preferences.get('accessibility'):
        result('Accessibility preference',all(d.width>=3 for d in layout.doors),'Circulation is connected, but local accessibility rules and turning clearances require professional review.',warning=True)
    return checks

def _relationship_score(layout, spec):
    if not spec.relationships: return 100
    scores = []
    for rel in spec.relationships:
        aa = match_rooms(layout, rel.source)
        bb = match_rooms(layout, rel.target)
        if not aa or not bb:
            scores.append(0)
            continue
        rel_scores = []
        for a in aa:
            for b in bb:
                if a.id == b.id: continue
                shared_length = bounds(a).boundary.intersection(bounds(b).boundary).length if a.floor==b.floor else 0.0
                dist = bounds(a).distance(bounds(b))
                r = str(rel.relation.value if hasattr(rel.relation,'value') else rel.relation)
                if r in ('connected','attached','accessible_from','accessed_from', 'open_to', 'adjacent'):
                    if a.floor != b.floor:
                        rel_scores.append(0)
                    else:
                        rel_scores.append(min(100, shared_length * 10))
                elif r in ('must_not_be_adjacent','separated'):
                    if a.floor != b.floor:
                        rel_scores.append(100)
                    else:
                        rel_scores.append(100 if dist > 0.1 else 0)
                elif r == 'away_from':
                    if a.floor != b.floor:
                        rel_scores.append(100)
                    else:
                        rel_scores.append(min(100, max(0, dist * 5)))
                elif r in ('near','preferred_near'):
                    if a.floor != b.floor:
                        rel_scores.append(0)
                    else:
                        rel_scores.append(max(0, 100 - dist * 5))
                else:
                    rel_scores.append(min(100, shared_length * 10))
        scores.append(max(rel_scores) if rel_scores else 0)
    return sum(scores) / len(scores) if scores else 100

def _compute_strategy_score(layout):
    strategy = layout.strategy
    if strategy == 'UNKNOWN' or not strategy: return 100
    score = 100
    bx, by, maxx, maxy = layout.footprint.bounding_box if layout.footprint else (0, 0, layout.width, layout.length)
    cx, cy = bx + (maxx - bx)/2, by + (maxy - by)/2
    
    for r in layout.rooms:
        cat = r.category if hasattr(r, 'category') else default_room_category(r.type)
        r_cx = r.x + r.width/2
        r_cy = r.y + r.height/2
        
        if strategy == 'PUBLIC_CENTRAL' and cat == RoomCategory.PUBLIC:
            dist = hypot(r_cx - cx, r_cy - cy)
            score += max(-20, min(20, 20 - dist))
            
    return max(0, min(100, score))

def score(layout,spec,score_weights=None):
    weights_dict = score_weights or DEFAULT_SCORE_WEIGHTS
    requirement=100 if not any(c.status=='ERROR' for c in layout.checks) else 0
    adjacency=_relationship_score(layout,spec)
    area=[]
    scale=3.280839895 if spec.unit=='meters' else 1
    for req in spec.rooms:
        for r in match_rooms(layout,req.name):
            target=(req.preferred_area*scale**2 if req.preferred_area else MIN_AREA[req.type]*1.25)
            actual=bounds(r).area
            area.append(min(actual/target,target/actual)*100)
    area_score=sum(area)/len(area) if area else 100
    circulation=100 if next(c for c in layout.checks if c.name=='All rooms accessible').status=='PASS' else 0
    footprint_area=footprint_polygon(layout.footprint).area if layout.footprint else layout.width*layout.length
    efficiency=100*sum(bounds(r).area for r in layout.rooms if r.type not in ('hall','stair'))/(footprint_area*layout.floors)
    habitable=[r for r in layout.rooms if r.type in ('bedroom','living','kitchen','office')]
    lighting=100*sum(any(w.room==r.id for w in layout.windows) for r in habitable)/max(1,len(habitable))
    private=[r for r in layout.rooms if r.type=='bedroom']
    exterior_ids={d.room_a for d in layout.doors if d.room_b is None}
    privacy=100*sum(r.id not in exterior_ids for r in private)/max(1,len(private))
    ventilation=100*sum(any(w.room==r.id for w in layout.windows) for r in habitable)/max(1,len(habitable))
    fp=footprint_polygon(layout.footprint) if layout.footprint else box(0,0,layout.width,layout.length)
    structural=max(0,100-(len(layout.footprint.boundary)-4)*4-(20 if layout.footprint.courtyard else 0))
    plot_utilization=100*fp.area/max(1,Polygon(layout.setback_boundary).area if layout.setback_boundary else layout.width*layout.length)
    strategy_score=_compute_strategy_score(layout)
    vals=[requirement,adjacency,area_score,circulation,efficiency,lighting,privacy,ventilation,structural,plot_utilization,strategy_score]
    keys=['requirement_score','adjacency_score','area_score','circulation_score','efficiency_score','lighting_score','privacy_score','ventilation_score','structural_score','plot_utilization_score','strategy_score']
    weights=[weights_dict.get(k, 0.1) for k in keys]
    return LayoutScore(**dict(zip(keys,[round(min(100,max(0,v)),1) for v in vals])),overall_score=round(sum(v*w for v,w in zip(vals,weights)),1))
