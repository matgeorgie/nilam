import test from 'node:test';
import assert from 'node:assert/strict';
import {exteriorWall,floorFinish,interiorWall,surfaceTexture} from '../lib/modelMaterials.ts';

test('room finishes share reusable architectural material definitions',()=>{
 assert.equal(floorFinish('bedroom'),floorFinish('living'));
 assert.equal(floorFinish('bedroom').pattern,'wood');
 assert.equal(floorFinish('bathroom').pattern,'tile');
 assert.equal(floorFinish('parking').pattern,'concrete');
 assert.equal(floorFinish('balcony').pattern,'deck');
 assert.equal(interiorWall.pattern,'plaster');
 assert.ok(exteriorWall.roughness>.8);
});

test('procedural textures are browser-only and safe during server-side import',()=>{
 assert.equal(surfaceTexture('wood'),null);
});
