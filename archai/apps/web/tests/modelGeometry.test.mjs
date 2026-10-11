import test from 'node:test';
import assert from 'node:assert/strict';
import {FLOOR_THICKNESS,roomFloorGeometry,wallPartTransform,wallPoint} from '../lib/modelGeometry.ts';

function topArea(geometry,top){
 const positions=geometry.getAttribute('position');let area=0;
 for(let i=0;i<positions.count;i+=3){
  const a=[positions.getX(i),positions.getY(i),positions.getZ(i)];
  const b=[positions.getX(i+1),positions.getY(i+1),positions.getZ(i+1)];
  const c=[positions.getX(i+2),positions.getY(i+2),positions.getZ(i+2)];
  if([a,b,c].every(point=>Math.abs(point[1]-top)<1e-5))
   area+=Math.abs((b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0]))/2;
 }
 return area;
}

test('a concave room floor uses its polygon, not its bounding rectangle',()=>{
 const room={x:0,y:0,width:6,height:6,polygon:[[0,0],[6,0],[6,2],[2,2],[2,6],[0,6]]};
 const geometry=roomFloorGeometry(room,10);
 try{
  geometry.computeBoundingBox();
  assert.equal(topArea(geometry,10+FLOOR_THICKNESS/2),20);
  assert.deepEqual([geometry.boundingBox.min.x,geometry.boundingBox.max.x,geometry.boundingBox.min.z,geometry.boundingBox.max.z],[0,6,0,6]);
 }finally{geometry.dispose()}
});

test('rooms without polygons retain a rectangular floor',()=>{
 const geometry=roomFloorGeometry({x:2,y:3,width:4,height:5},0);
 try{assert.equal(topArea(geometry,FLOOR_THICKNESS/2),20)}finally{geometry.dispose()}
});

test('wall geometry retains its thickness, floor offset and orientation',()=>{
 const wall={id:'w',floor:1,x1:5,y1:2,x2:5,y2:12,exterior:false,thickness:.5};
 assert.deepEqual(wallPoint(wall,3),[5,5]);
 const part=wallPartTransform(wall,{start:2,end:6,bottom:0,top:4.8});
 assert.deepEqual(part.position,[5,12.4,6]);
 assert.deepEqual(part.size,[4,4.8,.5]);
 assert.equal(part.rotation[1],-Math.PI/2);
});

test('a wall opening anchor follows the actual wall direction',()=>{
 const wall={x1:1,y1:2,x2:5,y2:5};
 assert.deepEqual(wallPoint(wall,2.5),[3,3.5]);
});
