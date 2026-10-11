"""Shared conceptual stair dimensions and checks; units are feet."""
from shapely.geometry import box,LineString
from shapely.ops import unary_union
from .schemas import Check

def entry_edge(s):
    if s.direction=='south':return LineString([(s.x,s.y),(s.x+s.width,s.y)])
    if s.direction=='north':return LineString([(s.x,s.y+s.length),(s.x+s.width,s.y+s.length)])
    if s.direction=='east':return LineString([(s.x,s.y),(s.x,s.y+s.length)])
    return LineString([(s.x+s.width,s.y),(s.x+s.width,s.y+s.length)])

def landing_zone(s):
    d=s.landing_depth
    if s.direction=='south':return box(s.x,s.y-d,s.x+s.width,s.y)
    if s.direction=='north':return box(s.x,s.y+s.length,s.x+s.width,s.y+s.length+d)
    if s.direction=='east':return box(s.x-d,s.y,s.x,s.y+s.length)
    return box(s.x+s.width,s.y,s.x+s.width+d,s.y+s.length)

def stair_checks(layout):
    from .layout import bounds,wall_line
    checks=[]
    def check(name,ok,detail):checks.append(Check(name=name,status='PASS' if ok else 'ERROR',detail=detail))
    for s in layout.stairs:
        zone=box(s.x,s.y,s.x+s.width,s.y+s.length)
        clear=all(bounds(r).intersection(zone).area<1e-5 for r in layout.rooms if r.floor in (s.from_floor,s.to_floor) and r.type!='stair')
        check('Stairwell reserved without room overlap',clear,'Stairs cannot occupy parking, habitable rooms, or the circulation floor slab.')
        transverse=s.width if s.direction in ('north','south') else s.length
        run=(s.length if s.direction in ('north','south') else s.width)-s.landing_depth
        check('Stair flight and turn dimensions',s.kind=='dogleg' and s.risers>=16 and s.risers%2==0 and (transverse-1)/2>=3.5 and s.landing_depth>=3.5 and run/(s.risers/2-1)>=.83 and 10/s.risers<=.625,'Return stair: 3.5 ft minimum flight, level turn, consistent risers/treads for a 10 ft storey. Conceptual checks, not local-code certification.')
        land=landing_zone(s);edge=entry_edge(s)
        for floor in (s.from_floor,s.to_floor):
            halls=[bounds(r) for r in layout.rooms if r.floor==floor and r.type=='hall']
            covered=bool(halls) and unary_union(halls).buffer(1e-5).covers(land)
            wallblock=sum(wall_line(w).intersection(edge).length for w in layout.walls if w.floor==floor)
            check(f'Level stair landing on floor {floor+1}',covered and wallblock<.1,'A separate unobstructed level landing must meet both flights; no wall or slab across the stair opening.')
    return checks

def stair_boxes(s):
    """Local transverse/depth coordinates, entry at depth zero; mirrored return flight."""
    transverse=s.width if s.direction in ('north','south') else s.length
    depth=s.length if s.direction in ('north','south') else s.width
    n=s.risers//2;run=depth-s.landing_depth;flight=(transverse-1)/2
    def world(u,v):
        if s.direction=='south':return s.x+u,s.y+v
        if s.direction=='north':return s.x+s.width-u,s.y+s.length-v
        if s.direction=='east':return s.x+v,s.y+s.length-u
        return s.x+s.width-v,s.y+u
    def part(u,v,w,d,h):
        x,y=world(u,v);thickness=.22
        size=(w,thickness,d) if s.direction in ('north','south') else (d,thickness,w)
        return size,(x,s.from_floor*10+h-thickness/2,y)
    if s.kind!='dogleg':
        for i in range(s.risers):yield part(transverse/2,depth-(i+.5)*depth/s.risers,transverse,depth/s.risers,(i+1)*10/s.risers)
        return
    for i in range(n-1):
        yield part(flight/2,(i+.5)*run/(n-1),flight,run/(n-1),(i+1)*10/s.risers)
        yield part(transverse-flight/2,run-(i+.5)*run/(n-1),flight,run/(n-1),(n+i+1)*10/s.risers)
    yield part(transverse/2,run+s.landing_depth/2,transverse,s.landing_depth,5)
