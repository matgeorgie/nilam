import type {Stair} from './types';
export type StairPart={position:[number,number,number];size:[number,number,number]};
export function stairParts(s:Stair):StairPart[]{
 const transverse=['north','south'].includes(s.direction)?s.width:s.length;
 const depth=['north','south'].includes(s.direction)?s.length:s.width;
 const parts:StairPart[]=[];
 function add(u:number,v:number,w:number,d:number,h:number){
  let x:number,z:number;
  if(s.direction==='south'){x=s.x+u;z=s.y+v;}
  else if(s.direction==='north'){x=s.x+s.width-u;z=s.y+s.length-v;}
  else if(s.direction==='east'){x=s.x+v;z=s.y+s.length-u;}
  else{x=s.x+s.width-v;z=s.y+u;}
  parts.push({position:[x,s.from_floor*10+h-.11,z],size:['north','south'].includes(s.direction)?[w,.22,d]:[d,.22,w]});
 }
 const risers=s.risers||18;
 if(s.kind!=='dogleg'){
  for(let i=0;i<risers;i++)add(transverse/2,depth-(i+.5)*depth/risers,transverse,depth/risers,(i+1)*10/risers);
  return parts;
 }
 const n=risers/2,landing=s.landing_depth||4,run=depth-landing,flight=(transverse-1)/2;
 for(let i=0;i<n-1;i++){
  add(flight/2,(i+.5)*run/(n-1),flight,run/(n-1),(i+1)*10/risers);
  add(transverse-flight/2,run-(i+.5)*run/(n-1),flight,run/(n-1),(n+i+1)*10/risers);
 }
 add(transverse/2,run+landing/2,transverse,landing,5);
 return parts;
}
