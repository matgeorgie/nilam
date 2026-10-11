import {ExtrudeGeometry,Shape} from 'three';
import type {Room,Wall} from './types';

export const FLOOR_HEIGHT=10;
export const FLOOR_THICKNESS=.32;
type Point=[number,number];
export type WallPart={start:number;end:number;bottom:number;top:number};

export function roomOutline(room:Pick<Room,'polygon'|'x'|'y'|'width'|'height'>):Point[]{
 if(room.polygon&&room.polygon.length>=3)return room.polygon;
 return [[room.x,room.y],[room.x+room.width,room.y],[room.x+room.width,room.y+room.height],[room.x,room.y+room.height]];
}

export function roomFloorGeometry(room:Pick<Room,'polygon'|'x'|'y'|'width'|'height'>,floorBase:number):ExtrudeGeometry{
 const outline=roomOutline(room);
 const shape=new Shape();
 shape.moveTo(outline[0][0],-outline[0][1]);
 for(const [x,y] of outline.slice(1))shape.lineTo(x,-y);
 shape.closePath();
 const geometry=new ExtrudeGeometry(shape,{depth:FLOOR_THICKNESS,bevelEnabled:false,curveSegments:1});
 geometry.rotateX(-Math.PI/2);
 geometry.translate(0,floorBase-FLOOR_THICKNESS/2,0);
 return geometry;
}

export function wallPoint(wall:Pick<Wall,'x1'|'y1'|'x2'|'y2'>,distance:number):Point{
 const length=Math.hypot(wall.x2-wall.x1,wall.y2-wall.y1);
 if(length<=0)throw new Error('A wall must have nonzero length.');
 return [wall.x1+(wall.x2-wall.x1)*distance/length,wall.y1+(wall.y2-wall.y1)*distance/length];
}

export function wallPartTransform(wall:Wall,part:WallPart):{position:[number,number,number];size:[number,number,number];rotation:[number,number,number]}{
 const length=Math.hypot(wall.x2-wall.x1,wall.y2-wall.y1);
 if(length<=0||part.end<=part.start||part.top<=part.bottom)throw new Error('Invalid wall span.');
 const [x,z]=wallPoint(wall,(part.start+part.end)/2);
 return {
  position:[x,wall.floor*FLOOR_HEIGHT+(part.bottom+part.top)/2,z],
  size:[part.end-part.start,part.top-part.bottom,wall.thickness||(wall.exterior?.42:.24)],
  rotation:[0,-Math.atan2(wall.y2-wall.y1,wall.x2-wall.x1),0],
 };
}
