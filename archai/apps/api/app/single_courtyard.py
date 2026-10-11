"""Measured one-storey courtyard profile; a true hole and walkable ring."""
from collections import Counter
from shapely.geometry import Polygon
from .schemas import HouseLayout,HouseFootprint,RoomGeometry,Window
from .layout import InfeasibleLayout,MIN_AREA,build_walls,shared_wall,wall_line,add_door,vehicle_gate_wall,validate,score,road_edge

class SingleCourtyardEngine:
    @staticmethod
    def supports(s):
        counts=Counter()
        for r in s.rooms:counts[r.type]+=r.count
        scale=3.280839895 if s.unit=='meters' else 1
        uw=((s.plot_width or 0)-s.setbacks.left_setback-s.setbacks.right_setback)*scale
        ul=((s.plot_length or 0)-s.setbacks.front_setback-s.setbacks.rear_setback)*scale
        W,L=(ul,uw) if s.road_location in ('east','west') else (uw,ul)
        return (s.floors==1 and s.shape=='courtyard' and not s.plot_polygon
                and s.plot_width is not None and s.plot_length is not None
                and W>=48 and L>=58
                and counts['porch']<=1 and 2<=counts['bedroom']<=4 and {k:v for k,v in counts.items() if k not in ('porch','bedroom')}=={'bathroom':2,'living':1,'dining':1,'kitchen':1,'utility':1}
                and s.parking_spaces==1 and not s.shape_parameters
                and not any(r.attached_bathroom or r.exact_width or r.exact_length or r.preferred_floor not in (None,0) for r in s.rooms))

    def generate(self,s,candidate_evaluator=None):
        if s.road_location!='north':
            return self._rotated(s,candidate_evaluator)
        scale=3.280839895 if s.unit=='meters' else 1
        pw,pl=s.plot_width*scale,s.plot_length*scale
        bx,by=s.setbacks.left_setback*scale,s.setbacks.front_setback*scale
        W=min(54,pw-bx-s.setbacks.right_setback*scale);L=min(64,pl-by-s.setbacks.rear_setback*scale)
        rooms=[];counts=Counter();requirements={}
        for req in s.rooms:requirements.setdefault(req.type,[]).extend([req]*req.count)
        def add(kind,name,x,y,w,h):
            i=counts[kind];counts[kind]+=1;req=requirements.get(kind,[])
            minimum=max(MIN_AREA.get(kind,0),((req[i].minimum_area or 0)*scale**2 if req else 0))
            if w*h<minimum:raise InfeasibleLayout(f'{name} cannot fit its requested minimum area.')
            r=RoomGeometry(id=f'{kind}-{i+1}',name=(req[i].name+(f' {i+1}' if req[i].count>1 else '') if req else name),type=kind,floor=0,x=bx+x,y=by+y,width=w,height=h,minimum_area=minimum)
            rooms.append(r);return r
        parking=add('parking','Car porch',0,0,10,18)
        porch=add('porch','Entrance sit-out',10,0,W-10,5)
        living=add('living','Living room',10,5,W-10,13)
        front=add('hall','Courtyard front passage',14,18,W-28,4)
        left=add('hall','Courtyard west passage',14,22,4,L-42)
        right=add('hall','Courtyard east passage',W-18,22,4,L-42)
        rear=add('hall','Private rear passage',0,L-20,W,4)
        baths=[add('bathroom',f'Shared bathroom {i+1}',0,18+i*8,14,8) for i in range(2)]
        utility=add('utility','Utility room',0,34,14,L-54)
        dining=add('dining','Dining area',W-14,18,14,13)
        kitchen=add('kitchen','Kitchen',W-14,31,14,L-51)
        bed_count=sum(r.count for r in s.rooms if r.type=='bedroom')
        beds=[add('bedroom',f'Bedroom {i+1}',i*W/bed_count,L-16,W/bed_count,16) for i in range(bed_count)]
        boundary=[(bx,by),(bx+W,by),(bx+W,by+L),(bx,by+L)]
        court=[(bx+18,by+22),(bx+W-18,by+22),(bx+W-18,by+L-20),(bx+18,by+L-20)]
        setback=[(bx,by),(pw-s.setbacks.right_setback*scale,by),(pw-s.setbacks.right_setback*scale,pl-s.setbacks.rear_setback*scale),(bx,pl-s.setbacks.rear_setback*scale)]
        fp=HouseFootprint(shape='courtyard',plot_width=pw,plot_length=pl,boundary=boundary,courtyard=court,buildable_boundary=setback,bounding_box=(bx,by,bx+W,by+L),metrics={'W':W,'L':L,'side_w':18,'end_l':20,'footprint_area':W*L-Polygon(court).area,'buildable_area':Polygon(setback).area})
        layout=HouseLayout(width=pw,length=pl,floors=1,footprint=fp,plot_boundary=[(0,0),(pw,0),(pw,pl),(0,pl)],setback_boundary=setback,road_edge=road_edge('north',pw,pl),strategy='SINGLE_COURTYARD',rooms=rooms,walls=[],doors=[],windows=[],stairs=[])
        pairs=[(front,left),(front,right),(rear,left),(rear,right),(living,front),(living,dining),(dining,right)]
        if s.preferences.get('open_kitchen') is not False:pairs.append((dining,kitchen))
        build_walls(layout,s,extra_open_pairs={tuple(sorted((a.id,b.id))) for a,b in pairs})
        def connect(a,b,width=3):
            walls=shared_wall(layout,a,b)
            if not walls:raise InfeasibleLayout(f'No usable doorway for {a.name}.')
            wall=max(walls,key=lambda w:wall_line(w).length);add_door(layout,a,b,wall,min(width,wall_line(wall).length-.3))
        connect(porch,living,3.5)
        for r in beds:connect(r,rear)
        for r in baths+[utility]:connect(r,left)
        if s.preferences.get('open_kitchen') is False:connect(dining,kitchen)
        wall=max([w for w in shared_wall(layout,porch,exterior=True) if abs(w.y1-by)<1e-5 and abs(w.y2-by)<1e-5],key=lambda w:wall_line(w).length)
        add_door(layout,porch,None,wall,3.5)
        gate=vehicle_gate_wall(layout,parking,'north')
        if not gate:raise InfeasibleLayout('No driveway access.')
        add_door(layout,parking,None,gate,9,'vehicle')
        courtyard_walls=[w for w in shared_wall(layout,front,exterior=True) if Polygon(court).boundary.buffer(1e-5).covers(wall_line(w))]
        if not courtyard_walls:raise InfeasibleLayout('No courtyard access from the passage.')
        add_door(layout,front,None,max(courtyard_walls,key=lambda w:wall_line(w).length),4,'courtyard')
        for r in rooms:
            if r.type in ('parking','porch'):continue
            walls=[w for w in shared_wall(layout,r,exterior=True) if not any(d.wall==w.id for d in layout.doors)]
            if walls:
                w=max(walls,key=lambda w:wall_line(w).length);width=min(5,wall_line(w).length-1)
                layout.windows.append(Window(id=f'window-{r.id}',room=r.id,wall=w.id,position=(wall_line(w).length-width)/2,width=width))
        layout.checks=validate(layout,s)
        if candidate_evaluator:layout.checks.extend(candidate_evaluator(layout)[0])
        errors=[c.name for c in layout.checks if c.status=='ERROR']
        if errors:raise InfeasibleLayout('Courtyard validation failed: '+', '.join(errors))
        layout.score=score(layout,s);layout.candidate_count=1;layout.chosen_candidate_id='single-courtyard-1'
        return layout

    def _rotated(self,s,evaluator):
        from .schemas import SiteConstraints
        from .layout import bounds
        scale=3.280839895 if s.unit=='meters' else 1
        W,L=s.plot_width*scale,s.plot_length*scale;side=s.road_location
        canonical=s.model_copy(deep=True);canonical.road_location='north'
        f,b,l,r=s.setbacks.front_setback,s.setbacks.rear_setback,s.setbacks.left_setback,s.setbacks.right_setback
        if side=='south':
            point=lambda x,y:(W-x,L-y)
            values=(b,f,r,l)
        elif side=='east':
            point=lambda x,y:(W-y,x)
            canonical.plot_width,canonical.plot_length=s.plot_length,s.plot_width
            values=(r,l,f,b)
        else:
            point=lambda x,y:(y,L-x)
            canonical.plot_width,canonical.plot_length=s.plot_length,s.plot_width
            values=(l,r,b,f)
        canonical.setbacks=SiteConstraints(front_setback=values[0],rear_setback=values[1],left_setback=values[2],right_setback=values[3])
        layout=self.generate(canonical)
        for index,room in enumerate(layout.rooms):
            data=room.model_dump();data['polygon']=[point(*v) for v in room.polygon]
            layout.rooms[index]=RoomGeometry.model_validate(data)
        for wall in layout.walls:
            wall.x1,wall.y1=point(wall.x1,wall.y1);wall.x2,wall.y2=point(wall.x2,wall.y2)
        fp=layout.footprint
        fp.boundary=[point(*v) for v in fp.boundary];fp.courtyard=[point(*v) for v in fp.courtyard]
        fp.buildable_boundary=[point(*v) for v in fp.buildable_boundary]
        xs,ys=zip(*fp.boundary);fp.bounding_box=(min(xs),min(ys),max(xs),max(ys))
        fp.plot_width,fp.plot_length=W,L;fp.metrics['W']=max(xs)-min(xs);fp.metrics['L']=max(ys)-min(ys)
        layout.width,layout.length=W,L;layout.plot_boundary=[(0,0),(W,0),(W,L),(0,L)]
        layout.setback_boundary=[point(*v) for v in layout.setback_boundary];layout.road_edge=road_edge(side,W,L)
        layout.checks=validate(layout,s)
        if evaluator:layout.checks.extend(evaluator(layout)[0])
        if any(c.status=='ERROR' for c in layout.checks):raise InfeasibleLayout('The rotated courtyard does not satisfy access or site constraints.')
        layout.score=score(layout,s)
        return layout
