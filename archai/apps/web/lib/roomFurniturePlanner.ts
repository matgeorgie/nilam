import type {Layout,Room,Wall} from './types';

export type FurnitureKind='bed'|'wardrobe'|'sofa'|'coffee_table'|'media_unit'|'dining_set'|'counter'|'fridge'|'toilet'|'sink'|'shower'|'desk'|'washer'|'car'|'patio_set'|'plant';
export type FurnitureAsset={id:FurnitureKind;category:string;compatibleRooms:string[];dimensions:[number,number,number];minimumRoomSize:[number,number];preferredWallPlacement:boolean;clearanceFront:number;clearanceSide:number;rotationRules:number[];styleTags:string[]};
export type FurniturePlacement={id:string;kind:FurnitureKind;roomId:string;x:number;z:number;width:number;depth:number;rotation:number};

const quarterTurns=[0,Math.PI/2];
export const furnitureCatalog:FurnitureAsset[]=[
 {id:'bed',category:'sleep',compatibleRooms:['bedroom'],dimensions:[5.2,6.6,1.6],minimumRoomSize:[8,9],preferredWallPlacement:true,clearanceFront:.7,clearanceSide:.45,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'wardrobe',category:'storage',compatibleRooms:['bedroom'],dimensions:[3.5,1.5,4.8],minimumRoomSize:[9,10],preferredWallPlacement:true,clearanceFront:.8,clearanceSide:.25,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'sofa',category:'seating',compatibleRooms:['living'],dimensions:[6,2.2,2.5],minimumRoomSize:[9,10],preferredWallPlacement:true,clearanceFront:.8,clearanceSide:.4,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'coffee_table',category:'table',compatibleRooms:['living'],dimensions:[3,1.8,1.3],minimumRoomSize:[9,10],preferredWallPlacement:false,clearanceFront:.5,clearanceSide:.4,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'media_unit',category:'storage',compatibleRooms:['living'],dimensions:[4,1.2,1.8],minimumRoomSize:[10,11],preferredWallPlacement:true,clearanceFront:.5,clearanceSide:.2,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'dining_set',category:'dining',compatibleRooms:['dining'],dimensions:[5.8,6.4,2.8],minimumRoomSize:[7,8],preferredWallPlacement:false,clearanceFront:.3,clearanceSide:.3,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'counter',category:'kitchen',compatibleRooms:['kitchen'],dimensions:[5,1.8,2.9],minimumRoomSize:[7,8],preferredWallPlacement:true,clearanceFront:.75,clearanceSide:.2,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'fridge',category:'kitchen',compatibleRooms:['kitchen'],dimensions:[2.2,2.2,5.8],minimumRoomSize:[8,9],preferredWallPlacement:true,clearanceFront:.7,clearanceSide:.2,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'toilet',category:'bath',compatibleRooms:['bathroom'],dimensions:[1.5,2,2.3],minimumRoomSize:[4,6],preferredWallPlacement:true,clearanceFront:.35,clearanceSide:.15,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'sink',category:'bath',compatibleRooms:['bathroom'],dimensions:[1.6,1.3,2.7],minimumRoomSize:[4,6],preferredWallPlacement:true,clearanceFront:.35,clearanceSide:.15,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'shower',category:'bath',compatibleRooms:['bathroom'],dimensions:[2.2,2.2,6.5],minimumRoomSize:[5,7],preferredWallPlacement:true,clearanceFront:.15,clearanceSide:.1,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'desk',category:'work',compatibleRooms:['office'],dimensions:[4.2,2,2.6],minimumRoomSize:[7,8],preferredWallPlacement:true,clearanceFront:.7,clearanceSide:.3,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'washer',category:'utility',compatibleRooms:['utility'],dimensions:[2,2,3],minimumRoomSize:[4,6],preferredWallPlacement:true,clearanceFront:.5,clearanceSide:.2,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'car',category:'vehicle',compatibleRooms:['parking'],dimensions:[6,12,4.5],minimumRoomSize:[8,16],preferredWallPlacement:false,clearanceFront:.4,clearanceSide:.4,rotationRules:quarterTurns,styleTags:['residential']},
 {id:'patio_set',category:'outdoor',compatibleRooms:['balcony','veranda','porch'],dimensions:[4,4,2.5],minimumRoomSize:[6,6],preferredWallPlacement:false,clearanceFront:.3,clearanceSide:.3,rotationRules:quarterTurns,styleTags:['outdoor']},
 {id:'plant',category:'decor',compatibleRooms:['living','balcony','veranda','porch'],dimensions:[2,2,3],minimumRoomSize:[9,9],preferredWallPlacement:true,clearanceFront:.1,clearanceSide:.1,rotationRules:quarterTurns,styleTags:['outdoor','residential']},
];

const EPS=1e-6;
function polygon(room:Room):[number,number][]{return room.polygon&&room.polygon.length>=3?room.polygon:[[room.x,room.y],[room.x+room.width,room.y],[room.x+room.width,room.y+room.height],[room.x,room.y+room.height]]}
function cross(a:[number,number],b:[number,number],c:[number,number]){return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])}
function inside(point:[number,number],outline:[number,number][]):boolean{
 let result=false;
 for(let i=0,j=outline.length-1;i<outline.length;j=i++){
  const a=outline[i],b=outline[j];
  if(Math.abs(cross(a,b,point))<EPS&&point[0]>=Math.min(a[0],b[0])-EPS&&point[0]<=Math.max(a[0],b[0])+EPS&&point[1]>=Math.min(a[1],b[1])-EPS&&point[1]<=Math.max(a[1],b[1])+EPS)return true;
  if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])result=!result;
 }
 return result;
}
function intersects(a:[number,number],b:[number,number],c:[number,number],d:[number,number]){return cross(a,b,c)*cross(a,b,d)<-EPS&&cross(c,d,a)*cross(c,d,b)<-EPS}
function dimensions(asset:FurnitureAsset,rotation:number):[number,number]{return rotation===0?[asset.dimensions[0],asset.dimensions[1]]:[asset.dimensions[1],asset.dimensions[0]]}
function fits(room:Room,x:number,z:number,width:number,depth:number,margin:number){
 const outline=polygon(room),hw=width/2+margin,hd=depth/2+margin;
 const corners:[number,number][]=[[x-hw,z-hd],[x+hw,z-hd],[x+hw,z+hd],[x-hw,z+hd]];
 if(!corners.every(corner=>inside(corner,outline)))return false;
 for(let i=0;i<4;i++)for(let j=0;j<outline.length;j++)if(intersects(corners[i],corners[(i+1)%4],outline[j],outline[(j+1)%outline.length]))return false;
 return true;
}
function openingCenter(wall:Wall,position:number,width:number):[number,number]{const length=Math.hypot(wall.x2-wall.x1,wall.y2-wall.y1),ratio=(position+width/2)/length;return [wall.x1+(wall.x2-wall.x1)*ratio,wall.y1+(wall.y2-wall.y1)*ratio]}
function nearRectangle(x:number,z:number,width:number,depth:number,px:number,pz:number,radius:number){return Math.hypot(Math.max(0,Math.abs(px-x)-width/2),Math.max(0,Math.abs(pz-z)-depth/2))<radius}

export function planRoomFurniture(layout:Pick<Layout,'unit'|'rooms'|'walls'|'doors'|'windows'>,room:Room):FurniturePlacement[]{
 const scale=layout.unit==='meters'?.3048:1;
 const assets=furnitureCatalog.filter(asset=>asset.compatibleRooms.includes(room.type));
 const walls=new Map(layout.walls.map(wall=>[wall.id,wall]));
 const doorZones=layout.doors.filter(door=>door.room_a===room.id||door.room_b===room.id).map(door=>{const wall=walls.get(door.wall);return wall?{center:openingCenter(wall,door.position,door.width),radius:door.kind==='vehicle'?scale:Math.max(1.3*scale,door.width*.45)}:null}).filter(zone=>zone!==null);
 const windowZones=layout.windows.filter(window=>window.room===room.id).map(window=>{const wall=walls.get(window.wall);return wall?{center:openingCenter(wall,window.position,window.width),radius:window.width/2+.4*scale}:null}).filter(zone=>zone!==null);
 const placed:FurniturePlacement[]=[];
 for(const asset of assets){
  if(Math.min(room.width,room.height)<Math.min(...asset.minimumRoomSize)*scale||Math.max(room.width,room.height)<Math.max(...asset.minimumRoomSize)*scale)continue;
  const candidates:{x:number;z:number;width:number;depth:number;rotation:number;score:number}[]=[];
  for(const rotation of asset.rotationRules){
   const [feetWidth,feetDepth]=dimensions(asset,rotation),width=feetWidth*scale,depth=feetDepth*scale,margin=.18*scale;
   for(let x=room.x+width/2+margin;x<=room.x+room.width-width/2-margin+EPS;x+=.75*scale)
    for(let z=room.y+depth/2+margin;z<=room.y+room.height-depth/2-margin+EPS;z+=.75*scale){
     const wallDistance=Math.min(x-width/2-room.x,room.x+room.width-x-width/2,z-depth/2-room.y,room.y+room.height-z-depth/2);
     const centerDistance=Math.hypot(x-room.x-room.width/2,z-room.y-room.height/2);
     const score=asset.preferredWallPlacement?wallDistance+.04*centerDistance:centerDistance;
     candidates.push({x,z,width,depth,rotation,score});
    }
  }
  candidates.sort((a,b)=>a.score-b.score||a.z-b.z||a.x-b.x||a.rotation-b.rotation);
  const chosen=candidates.find(candidate=>{
   if(!fits(room,candidate.x,candidate.z,candidate.width,candidate.depth,Math.max(asset.clearanceSide,.18)*scale))return false;
   if(asset.id!=='car'&&doorZones.some(zone=>nearRectangle(candidate.x,candidate.z,candidate.width,candidate.depth,...zone.center,zone.radius)))return false;
   if(asset.dimensions[2]>3.5&&windowZones.some(zone=>nearRectangle(candidate.x,candidate.z,candidate.width,candidate.depth,...zone.center,zone.radius)))return false;
   return placed.every(other=>Math.abs(candidate.x-other.x)>=(candidate.width+other.width)/2+asset.clearanceSide*scale||Math.abs(candidate.z-other.z)>=(candidate.depth+other.depth)/2+asset.clearanceFront*scale);
  });
  if(chosen)placed.push({id:`${room.id}-${asset.id}`,kind:asset.id,roomId:room.id,x:chosen.x,z:chosen.z,width:chosen.width,depth:chosen.depth,rotation:chosen.rotation});
 }
 return placed;
}
