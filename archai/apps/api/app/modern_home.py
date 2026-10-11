"""Constrained duplex planning: reserve a stair core before allocating rooms.
Canonical plan faces north; rotate the complete topology for the road edge.
"""
from collections import Counter
from .schemas import HouseLayout, HouseFootprint, RoomGeometry, Stair, Window, Check
from .layout import (InfeasibleLayout, MIN_AREA, build_walls, shared_wall, wall_line,
                     add_door, vehicle_gate_wall, validate, score, road_edge, bounds)

class ModernHomeLayoutEngine:
    @staticmethod
    def supports(spec):
        counts=Counter()
        for r in spec.rooms: counts[r.type]+=r.count
        scale=3.280839895 if spec.unit=='meters' else 1
        w=(spec.plot_width or 0)*scale-(spec.setbacks.left_setback+spec.setbacks.right_setback)*scale
        l=(spec.plot_length or 0)*scale-(spec.setbacks.front_setback+spec.setbacks.rear_setback)*scale
        if spec.road_location in ('east','west'):w,l=l,w
        return (spec.floors==2 and spec.shape in ('auto','rectangle') and not spec.plot_polygon
                and 28<=w<=48 and 44<=l<=65 and spec.parking_spaces in (0,1)
                and set(counts)<={'bedroom','bathroom','living','dining','kitchen','utility','balcony','porch'}
                and all(counts[k]==1 for k in ('living','dining','kitchen'))
                and 1<=counts['bedroom']<=4 and counts['bathroom']<=3 and counts['utility']<=1
                and counts['porch']<=1 and counts['balcony']<=2 and not any(r.exact_width or r.exact_length for r in spec.rooms)
                and not any(r.type in ('living','dining','kitchen','utility') and r.preferred_floor not in (None,0) for r in spec.rooms))

    def generate(self,spec,candidate_evaluator=None):
        scale=3.280839895 if spec.unit=='meters' else 1
        pw,pl=spec.plot_width*scale,spec.plot_length*scale
        ox,oy=spec.setbacks.left_setback*scale,spec.setbacks.front_setback*scale
        uw=pw-ox-spec.setbacks.right_setback*scale;ul=pl-oy-spec.setbacks.rear_setback*scale
        side=spec.road_location;W,L=(ul,uw) if side in ('east','west') else (uw,ul)
        # Do not stretch rooms indefinitely to fill the site.
        L=min(L, max(50 if any(r.type=='bedroom' and r.preferred_floor==0 for r in spec.rooms) else 44, min(3,sum(r.count for r in spec.rooms if r.type=='bedroom'))*16))
        def point(x,y):
            if side=='south':return (ox+uw-x,oy+ul-y)
            if side=='west':return (ox+y,oy+ul-x)
            if side=='east':return (ox+uw-y,oy+x)
            return (ox+x,oy+y)
        rooms=[];pairs=set();links=[];counters=Counter()
        def add(kind,name,f,x,y,w,h,req=None,rid=None):
            counters[kind]+=1;rid=rid or f'{kind}-{counters[kind]}'
            poly=[point(x,y),point(x+w,y),point(x+w,y+h),point(x,y+h)]
            xs,ys=zip(*poly)
            minimum=max(MIN_AREA.get(kind,0),(req.minimum_area or 0)*scale**2 if req else 0)
            if w*h+.01<minimum:raise InfeasibleLayout(f'{name} needs more area in the reserved-core plan. Increase plot size or reduce rooms.')
            r=RoomGeometry(id=rid,name=name,type=kind,floor=f,x=min(xs),y=min(ys),width=max(xs)-min(xs),height=max(ys)-min(ys),polygon=poly,minimum_area=minimum)
            rooms.append(r);return r
        def opened(a,b):pairs.add(tuple(sorted((a.id,b.id))))
        instances={k:[] for k in ('bedroom','bathroom','living','dining','kitchen','utility','balcony')}
        for req in spec.rooms:
            if req.type=='porch':continue
            for i in range(req.count):instances[req.type].append((req,req.name+(f' {i+1}' if req.count>1 else '')))
        def requested(kind,f,x,y,w,h):
            req,name=instances[kind].pop(0);return add(kind,name,f,x,y,w,h,req)
        ground_beds=[];upper_beds=[]
        for entry in instances['bedroom']:
            (ground_beds if entry[0].preferred_floor==0 else upper_beds).append(entry)
        if len(ground_beds)>1 or len(upper_beds)>3:
            raise InfeasibleLayout('This duplex supports one ground-floor bedroom and up to three upstairs. Specify preferred floors or reduce rooms.')
        parking=add('parking','Car porch',0,0,0,10,18) if spec.parking_spaces else None
        if not parking:add('veranda','Front terrace',0,0,0,10,18)
        porch=add('porch','Entrance sit-out',0,10,0,W-10,5,rid='porch-1')
        living=requested('living',0,10,5,W-10,13)
        dining=requested('dining',0,14,18,W-14,12)
        rear_start=40 if ground_beds else L
        kitchen=requested('kitchen',0,14,30,W-14,rear_start-30)
        hall0=add('hall','Family circulation',0,10,18,4,L-18,rid='hall-0-0')
        opened(living,dining);opened(living,hall0);opened(dining,hall0)
        if spec.preferences.get('open_kitchen') is False:links.append((dining,kitchen))
        else:opened(dining,kitchen)
        links.append((porch,living))
        def bedroom(req,name,f,x,y,w,h,hall):
            bath_w=5 if req.attached_bathroom else 0
            bed=add('bedroom',name,f,x,y,w-bath_w,h,req);links.append((bed,hall))
            if bath_w:
                bath=add('bathroom',name+' ensuite',f,x+w-bath_w,y,bath_w,h)
                bath.attached_to=bed.id;links.append((bed,bath))
        if ground_beds:
            req,name=ground_beds[0];bedroom(req,name,0,14,40,W-14,L-40,hall0)
        # Both floor landings are separate level rooms, never overlapping steps.
        halls=[hall0];stairs=[]
        upper_end=max(34,min(L,max(1,len(upper_beds))*16))
        hall1=add('hall','Upper circulation',1,10,0,4,upper_end,rid='hall-1-0');halls.append(hall1)
        for f in (0,1):
            landing=add('hall','Stair landing',f,0,18,10,4,rid=f'landing-{f}')
            core=add('stair','Enclosed return stair',f,0,22,10,12,rid=f'stair-{f}')
            opened(landing,halls[f]);opened(landing,core)
        core=next(r for r in rooms if r.id=='stair-0')
        direction={'north':'south','south':'north','west':'east','east':'west'}[side]
        stairs.append(Stair(id='stairs-0',from_floor=0,to_floor=1,x=core.x,y=core.y,width=core.width,length=core.height,direction=direction,kind='dogleg',landing_depth=4,risers=18))
        for i,(req,name) in enumerate(upper_beds):
            bedroom(req,name,1,14,i*16,W-14,16,hall1)
        # The unused front of the upper left wing is an explicit roof terrace.
        terrace_count=max(1,len(instances['balcony']))
        for i in range(terrace_count):
            terrace=add('balcony',instances['balcony'][i][1] if instances['balcony'] else 'Roof terrace',1,0,i*18/terrace_count,10,18/terrace_count)
            links.append((terrace,hall1))
        # Bathrooms are grouped in the rear service strip and stacked when possible.
        by_floor={0:[],1:[]}
        for i,entry in enumerate(instances['bathroom']):by_floor[entry[0].preferred_floor if entry[0].preferred_floor is not None else i%2].append(entry)
        for f in (0,1):
            extras=by_floor[f]+(instances['utility'] if f==0 else [])
            if extras:
                depth=(L-34)/len(extras)
                if depth<5:raise InfeasibleLayout('Rear service rooms need more depth.')
                if f==1 and upper_end<L:
                    rooms.remove(hall1);hall1=add('hall','Upper circulation',1,10,0,4,L,rid='hall-1-0');halls[1]=hall1
                for i,(req,name) in enumerate(extras):
                    room=add(req.type,name,f,0,34+i*depth,10,depth,req);links.append((room,halls[f]))
        # Room objects in links may refer to the replaced hall but its ID/geometry must be current.
        by_id={r.id:r for r in rooms};links=[(by_id[a.id],by_id[b.id]) for a,b in links]
        poly=[point(0,0),point(W,0),point(W,L),point(0,L)];xs,ys=zip(*poly)
        setback=[(ox,oy),(ox+uw,oy),(ox+uw,oy+ul),(ox,oy+ul)]
        fp=HouseFootprint(shape='rectangle',plot_width=pw,plot_length=pl,boundary=poly,buildable_boundary=setback,bounding_box=(min(xs),min(ys),max(xs),max(ys)),metrics={'W':max(xs)-min(xs),'L':max(ys)-min(ys),'footprint_area':W*L,'buildable_area':uw*ul})
        layout=HouseLayout(width=pw,length=pl,floors=2,rooms=rooms,walls=[],doors=[],windows=[],stairs=stairs,footprint=fp,plot_boundary=[(0,0),(pw,0),(pw,pl),(0,pl)],setback_boundary=setback,road_edge=road_edge(side,pw,pl),strategy='MODERN_DUPLEX')
        build_walls(layout,spec,extra_open_pairs=pairs)
        for a,b in links:
            walls=shared_wall(layout,a,b)
            if not walls:raise InfeasibleLayout(f'No level doorway between {a.name} and {b.name}.')
            wall=max(walls,key=lambda w:wall_line(w).length);add_door(layout,a,b,wall,width=3)
        from .layout import road_facing_wall
        entry=[w for w in shared_wall(layout,porch,exterior=True) if road_facing_wall(w,porch,side)]
        if not entry:raise InfeasibleLayout('No road-facing pedestrian entrance.')
        add_door(layout,porch,None,max(entry,key=lambda w:wall_line(w).length),width=3.5)
        if parking:
            gate=vehicle_gate_wall(layout,parking,side)
            if not gate:raise InfeasibleLayout('No unobstructed vehicle entry.')
            add_door(layout,parking,None,gate,width=9,kind='vehicle')
        else:
            front=next(r for r in rooms if r.type=='veranda');opened(front,porch)
            walls=shared_wall(layout,front,porch)
            if walls:add_door(layout,front,porch,walls[0],width=3)
        for r in rooms:
            if r.type not in ('bedroom','living','dining','kitchen','bathroom','utility'):continue
            walls=[w for w in shared_wall(layout,r,exterior=True) if not any(d.wall==w.id for d in layout.doors)]
            if walls:
                w=max(walls,key=lambda w:wall_line(w).length);size=min(4,wall_line(w).length-1)
                layout.windows.append(Window(id=f'window-{r.id}',room=r.id,wall=w.id,position=(wall_line(w).length-size)/2,width=size))
        layout.checks=validate(layout,spec)
        if not instances['bathroom']:layout.checks.append(Check(name='Bathroom missing from brief',status='WARNING',detail='No bathroom was requested. Add a shared bathroom before treating this as a usable home plan.'))
        if candidate_evaluator:
            checks,_=candidate_evaluator(layout);layout.checks.extend(checks)
        errors=[c.name for c in layout.checks if c.status=='ERROR']
        if errors:raise InfeasibleLayout('Reserved-core plan failed: '+', '.join(errors))
        layout.score=score(layout,spec);layout.chosen_candidate_id='modern-duplex-1';layout.candidate_count=1
        return layout
