import test from 'node:test';
import assert from 'node:assert/strict';
import {cameraFrame} from '../lib/modelCamera.ts';

const layout={width:30,length:50,floors:2,stairs:[{from_floor:0,to_floor:1}]};

test('the camera frames the plan in both wide and narrow viewports',()=>{
 for(const [width,height] of [[900,600],[390,600]]){
  const frame=cameraFrame(layout,0,width,height,10);
  assert.ok(frame.spanX*frame.zoom<=width*.84+1e-6);
  assert.ok(frame.spanY*frame.zoom<=height*.8+1e-6);
  assert.ok(frame.position[1]>frame.target[1]);
 }
});

test('all-floor view frames the vertical stack and centers on it',()=>{
 const single=cameraFrame(layout,0,900,600,10);
 const all=cameraFrame(layout,-1,900,600,10);
 assert.ok(all.zoom<=single.zoom);
 assert.equal(all.target[1],9.5);
});

test('upper floor centers on its own geometry and the arriving stair',()=>{
 const frame=cameraFrame(layout,1,900,600,10);
 assert.equal(frame.target[1],9.5);
 assert.ok(frame.zoom>0);
});
