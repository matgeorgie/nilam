import test from 'node:test';
import assert from 'node:assert/strict';
import {lightingFrame} from '../lib/modelLighting.ts';

test('sun shadow coverage scales with the plot and floor count',()=>{
 const small=lightingFrame({width:30,length:50,floors:1},10);
 const large=lightingFrame({width:50,length:80,floors:3},10);
 assert.ok(large.shadowExtent>small.shadowExtent);
 assert.ok(large.contactScale>small.contactScale);
 assert.ok(large.contactFar>small.contactFar);
 assert.ok(large.sunPosition[1]>small.sunPosition[1]);
});
