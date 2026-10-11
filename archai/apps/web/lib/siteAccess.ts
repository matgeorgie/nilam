import type {Layout} from './types';
export type SiteSide='north'|'south'|'east'|'west';
export function roadSide(layout:Layout):SiteSide{
 const edge=layout.road_edge;if(!edge)return 'south';
 const [a,b]=edge,mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2;
 return Math.abs(a[0]-b[0])>Math.abs(a[1]-b[1])?(my<layout.length/2?'north':'south'):(mx<layout.width/2?'west':'east');
}
export function siteAccess(layout:Layout){
 const side=roadSide(layout),horizontal=side==='north'||side==='south',span=horizontal?layout.width:layout.length;
 const gates=layout.doors.filter(d=>d.kind==='entry'||d.kind==='vehicle').flatMap(d=>{
  const wall=layout.walls.find(w=>w.id===d.wall);if(!wall||wall.floor!==0)return [];
  const len=Math.hypot(wall.x2-wall.x1,wall.y2-wall.y1),t=(d.position+d.width/2)/len;
  const x=wall.x1+(wall.x2-wall.x1)*t,z=wall.y1+(wall.y2-wall.y1)*t;
  return [{center:horizontal?x:z,width:d.kind==='vehicle'?Math.max(d.width,9):Math.max(d.width,4),x,z,kind:d.kind}];
 });
 const intervals=gates.map(g=>[g.center-g.width/2,g.center+g.width/2] as [number,number]).sort((a,b)=>a[0]-b[0]);
 const fence:[number,number][]=[];let cursor=-7;
 for(const [start,end] of intervals){if(start>cursor)fence.push([cursor,start]);cursor=Math.max(cursor,end)}
 if(cursor<span+7)fence.push([cursor,span+7]);
 return {side,horizontal,span,gates,fence};
}
