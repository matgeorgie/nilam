import type {Layout,Room} from './types';
import {siteAccess} from './siteAccess';
function inPolygon(x:number,z:number,polygon:number[][]){
 let inside=false;
 for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
  const [ax,az]=polygon[i],[bx,bz]=polygon[j];
  if((az>z)!==(bz>z)&&x<(bx-ax)*(z-az)/(bz-az)+ax)inside=!inside;
 }return inside;
}
export function insideRoom(x:number,z:number,r:Room){
 const polygon=r.polygon?.length?r.polygon:[[r.x,r.y],[r.x+r.width,r.y],[r.x+r.width,r.y+r.height],[r.x,r.y+r.height]];
 return inPolygon(x,z,polygon);
}
export function canWalk(layout:Layout,floor:number,x:number,z:number,radius=.55){
 const inRoom=layout.rooms.some(r=>r.floor===floor&&r.type!=='stair'&&insideRoom(x,z,r));
 if(!inRoom){
  if(floor!==0||x< -8+radius||z< -8+radius||x>layout.width+8-radius||z>layout.length+8-radius)return false;
  const boundary=layout.footprint?.boundary||[[0,0],[layout.width,0],[layout.width,layout.length],[0,layout.length]],court=layout.footprint?.courtyard;
  if(inPolygon(x,z,boundary)&&!(court&&inPolygon(x,z,court)))return false;
 }
 if(floor===0){
  const access=siteAccess(layout);
  for(const side of ['north','south','east','west']){
   const horizontal=side==='north'||side==='south',edge=side==='north'?-7:side==='south'?layout.length+7:side==='west'?-7:layout.width+7;
   const intervals=side===access.side?access.fence:[[-7,horizontal?layout.width+7:layout.length+7]];
   const along=horizontal?x:z,distance=Math.abs((horizontal?z:x)-edge);
   if(distance<radius+.125&&intervals.some(([a,b])=>along>a-radius&&along<b+radius))return false;
  }
 }
 // Windows block movement; actual door openings remain passable.
 for(const w of layout.walls.filter(w=>w.floor===floor)){
  const dx=w.x2-w.x1,dz=w.y2-w.y1,length=Math.hypot(dx,dz);if(!length)continue;
  const along=((x-w.x1)*dx+(z-w.y1)*dz)/length,clamped=Math.max(0,Math.min(length,along));
  const distance=Math.hypot(x-w.x1-dx*clamped/length,z-w.y1-dz*clamped/length);
  if(distance>=radius+(w.thickness||.5)/2)continue;
  if(!layout.doors.some(d=>d.wall===w.id&&along>d.position+radius&&along<d.position+d.width-radius))return false;
 }return true;
}
export function walkSpawn(layout:Layout,floor:number){
 const rooms=layout.rooms.filter(r=>r.floor===floor&&r.type!=='stair').sort((a,b)=>Number(!['hall','living','porch'].includes(a.type))-Number(!['hall','living','porch'].includes(b.type)));
 for(const r of rooms){
  const center:[number,number]=[r.x+r.width/2,r.y+r.height/2];if(canWalk(layout,floor,...center))return center;
  for(let z=r.y+1;z<r.y+r.height;z+=1)for(let x=r.x+1;x<r.x+r.width;x+=1)if(canWalk(layout,floor,x,z))return [x,z] as [number,number];
 }return null;
}
