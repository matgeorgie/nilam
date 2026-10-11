import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {siteAccess} from '../lib/siteAccess';
import {walkSpawn,canWalk} from '../lib/walkNavigation';
import type {Layout} from '../lib/types';
const layouts:Layout[]=JSON.parse(readFileSync('tests/fixtures/walk-layouts.json','utf8'));
test('all road sides get matching garden gates and traversable floor spawns',()=>{
 const sides=['north','south','east','west'];
 layouts.forEach((layout,i)=>{
  const access=siteAccess(layout);if(i<4)expect(access.side).toBe(sides[i]);
  expect(access.gates.some(g=>g.kind==='entry')).toBeTruthy();
  for(const gate of access.gates)expect(access.fence.some(([a,b])=>gate.center>a&&gate.center<b)).toBeFalsy();
  for(let floor=0;floor<layout.floors;floor++){
   const spawn=walkSpawn(layout,floor);expect(spawn).not.toBeNull();expect(canWalk(layout,floor,...spawn!)).toBeTruthy();
   expect(canWalk(layout,floor,-20,-20)).toBeFalsy();
   const wall=layout.walls.find(w=>w.floor===floor&&Math.hypot(w.x2-w.x1,w.y2-w.y1)>2&&!layout.doors.some(d=>d.wall===w.id));
   if(wall)expect(canWalk(layout,floor,(wall.x1+wall.x2)/2,(wall.y1+wall.y2)/2)).toBeFalsy();
   for(const d of layout.doors.filter(d=>{const w=layout.walls.find(w=>w.id===d.wall);return w?.floor===floor&&!!d.room_b})){
    const w=layout.walls.find(w=>w.id===d.wall)!,t=(d.position+d.width/2)/Math.hypot(w.x2-w.x1,w.y2-w.y1);
    // On a shared boundary either adjoining room must contain a nearby sample.
    const x=w.x1+(w.x2-w.x1)*t,z=w.y1+(w.y2-w.y1)*t;
    expect(canWalk(layout,floor,x+.02,z)||canWalk(layout,floor,x-.02,z)||canWalk(layout,floor,x,z+.02)||canWalk(layout,floor,x,z-.02)).toBeTruthy();
   }
  }
 });
});
