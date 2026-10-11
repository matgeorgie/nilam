import type {Layout} from './types';

type V3=[number,number,number];
const DIRECTION:V3=[.55,1.6,.65];

export function cameraFrame(layout:Pick<Layout,'width'|'length'|'floors'|'stairs'>,floor:number,viewportWidth:number,viewportHeight:number,floorHeight:number){
 const magnitude=Math.hypot(...DIRECTION);
 const direction:V3=DIRECTION.map(value=>value/magnitude) as V3;
 const horizontal=Math.hypot(direction[0],direction[2]);
 const right:V3=[direction[2]/horizontal,0,-direction[0]/horizontal];
 const up:V3=[direction[1]*right[2],horizontal,-direction[1]*right[0]];
 const floorBase=Math.max(0,floor)*floorHeight;
 const lower=floor<0?0:layout.stairs.some(stair=>stair.to_floor===floor)?floorBase-floorHeight:floorBase;
 const upper=floor<0?(layout.floors-1)*floorHeight+9:floorBase+(layout.stairs.some(stair=>stair.from_floor===floor)?floorHeight:9);
 const target:V3=[0,(lower+upper)/2,0];
 const halfX=layout.width/2,halfZ=layout.length/2;
 const corners:V3[]=[];
 for(const x of [-halfX,halfX])for(const y of [lower,upper])for(const z of [-halfZ,halfZ])corners.push([x,y-target[1],z]);
 const project=(point:V3,basis:V3)=>point[0]*basis[0]+point[1]*basis[1]+point[2]*basis[2];
 const xs=corners.map(point=>project(point,right)),ys=corners.map(point=>project(point,up));
 const spanX=Math.max(...xs)-Math.min(...xs),spanY=Math.max(...ys)-Math.min(...ys);
 const zoom=Math.max(.1,Math.min(Math.max(1,viewportWidth)*.84/Math.max(1,spanX),Math.max(1,viewportHeight)*.8/Math.max(1,spanY)));
 const distance=Math.max(layout.width,layout.length,upper-lower)*2;
 const position:V3=[target[0]+direction[0]*distance,target[1]+direction[1]*distance,target[2]+direction[2]*distance];
 return {position,target,zoom,spanX,spanY};
}
