import test from 'node:test';
import assert from 'node:assert/strict';
import {planRoomFurniture} from '../lib/roomFurniturePlanner.ts';

function room(type,width,height,polygon){return {id:`${type}-1`,name:type,type,floor:0,x:0,y:0,width,height,polygon,attached_to:null,minimum_area:0}}
function layout(unit,rooms,doors=[],windows=[],walls=[]){return {unit,rooms,doors,windows,walls}}
function inside([x,y],polygon){let hit=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){const a=polygon[i],b=polygon[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])hit=!hit}return hit}
function corners(p){return [[p.x-p.width/2,p.z-p.depth/2],[p.x+p.width/2,p.z-p.depth/2],[p.x+p.width/2,p.z+p.depth/2],[p.x-p.width/2,p.z+p.depth/2]]}

test('bedroom furniture stays inside a rectangular room and avoids the door',()=>{
 const r=room('bedroom',13,15);
 const wall={id:'door-wall',floor:0,x1:0,y1:0,x2:13,y2:0,exterior:false};
 const result=planRoomFurniture(layout('feet',[r],[{id:'door',room_a:r.id,room_b:null,wall:wall.id,position:5,width:3,swing_direction:'left'}],[],[wall]),r);
 assert.ok(result.some(item=>item.kind==='bed'));
 for(const p of result){for(const [x,z] of corners(p))assert.ok(x>=0&&x<=13&&z>=0&&z<=15);assert.ok(Math.hypot(Math.max(0,Math.abs(6.5-p.x)-p.width/2),Math.max(0,Math.abs(p.z)-p.depth/2))>=1.3)}
 for(let i=0;i<result.length;i++)for(let j=i+1;j<result.length;j++)assert.ok(Math.abs(result[i].x-result[j].x)>=(result[i].width+result[j].width)/2||Math.abs(result[i].z-result[j].z)>=(result[i].depth+result[j].depth)/2);
});

test('furniture does not fill the missing corner of a concave room',()=>{
 const outline=[[0,0],[14,0],[14,6],[7,6],[7,14],[0,14]];
 const r=room('living',14,14,outline);
 const result=planRoomFurniture(layout('feet',[r]),r);
 assert.ok(result.some(item=>item.kind==='sofa'));
 for(const p of result)for(const corner of corners(p))assert.ok(inside(corner,outline));
});

test('small bathroom omits furniture that does not fit',()=>{
 const r=room('bathroom',4,6);
 const result=planRoomFurniture(layout('feet',[r]),r);
 assert.ok(result.every(p=>p.kind!=='shower'));
});

test('meter layouts use converted real-world furniture dimensions',()=>{
 const r=room('bedroom',4,5);
 const result=planRoomFurniture(layout('meters',[r]),r);
 const bed=result.find(p=>p.kind==='bed');
 assert.ok(bed);
 assert.ok(Math.abs(Math.min(bed.width,bed.depth)-5.2*.3048)<1e-8);
});
