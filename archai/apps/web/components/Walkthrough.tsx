'use client';
import {useEffect,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {PerspectiveCamera} from '@react-three/drei';
import type {PerspectiveCamera as Camera} from 'three';
import type {Layout} from '@/lib/types';
import {canWalk,walkSpawn} from '@/lib/walkNavigation';
import {FLOOR_HEIGHT} from '@/lib/modelGeometry';
export default function Walkthrough({layout,floor,onExit}:{layout:Layout;floor:number;onExit:()=>void}){
 const ref=useRef<Camera>(null),keys=useRef(new Set<string>()),view=useRef({yaw:0,pitch:0,drag:false}),position=useRef<[number,number]>([0,0]);
 const {gl}=useThree();
 useEffect(()=>{const spawn=walkSpawn(layout,floor);if(!spawn){onExit();return}position.current=spawn;keys.current.clear()},[layout,floor,onExit]);
 useEffect(()=>{
  const target=gl.domElement;
  function down(e:KeyboardEvent){if((e.target as HTMLElement)?.closest('input,textarea,select'))return;if(e.key==='Escape'){onExit();return}if(['w','a','s','d','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();keys.current.add(e.key)}}
  function up(e:KeyboardEvent){keys.current.delete(e.key)}
  function mouseDown(){view.current.drag=true}
  function mouseUp(){view.current.drag=false}
  function move(e:MouseEvent){if(!view.current.drag)return;view.current.yaw-=e.movementX*.004;view.current.pitch=Math.max(-1.2,Math.min(1.2,view.current.pitch-e.movementY*.004))}
  function blur(){keys.current.clear();view.current.drag=false}
  window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',blur);target.addEventListener('mousedown',mouseDown);window.addEventListener('mouseup',mouseUp);window.addEventListener('mousemove',move);
  return()=>{delete target.dataset.walkPosition;delete target.dataset.walkFloor;window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',blur);target.removeEventListener('mousedown',mouseDown);window.removeEventListener('mouseup',mouseUp);window.removeEventListener('mousemove',move)};
 },[gl,onExit]);
 useFrame((_,delta)=>{
  if(!ref.current)return;const k=keys.current,v=view.current;
  const forward=Number(k.has('w')||k.has('ArrowUp'))-Number(k.has('s')||k.has('ArrowDown')),right=Number(k.has('d')||k.has('ArrowRight'))-Number(k.has('a')||k.has('ArrowLeft'));
  const speed=Math.min(delta,.04)*5/Math.max(1,Math.hypot(forward,right)),[x,z]=position.current;
  const nx=x+(-Math.sin(v.yaw)*forward+Math.cos(v.yaw)*right)*speed,nz=z+(-Math.cos(v.yaw)*forward-Math.sin(v.yaw)*right)*speed;
  if(canWalk(layout,floor,nx,z))position.current[0]=nx;
  if(canWalk(layout,floor,position.current[0],nz))position.current[1]=nz;
  ref.current.position.set(position.current[0]-layout.width/2,floor*FLOOR_HEIGHT+5.4,position.current[1]-layout.length/2);
  ref.current.rotation.set(v.pitch,v.yaw,0,'YXZ');
  gl.domElement.dataset.walkPosition=JSON.stringify(position.current);gl.domElement.dataset.walkFloor=String(floor);
 });
 return <PerspectiveCamera ref={ref} makeDefault fov={70} near={.08} far={1000}/>;
}
