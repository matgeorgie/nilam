'use client';

import {useEffect,useMemo,useRef,useState,Suspense} from 'react';
import {Canvas,useThree} from '@react-three/fiber';
import {ContactShadows, OrbitControls, OrthographicCamera,Environment,Lightformer} from '@react-three/drei';
import {ACESFilmicToneMapping,Group,DoubleSide,FrontSide} from 'three';
import type {Texture} from 'three';
import {GLTFExporter} from 'three/addons/exporters/GLTFExporter.js';
import DetailedFurniture from './DetailedFurniture';
import Walkthrough from './Walkthrough';
import {siteAccess} from '@/lib/siteAccess';
import type {Layout, Room} from '@/lib/types';
import {wallParts} from '@/lib/geometry';
import {stairParts} from '@/lib/stairGeometry';
import {FLOOR_HEIGHT,roomFloorGeometry,wallPartTransform,wallPoint} from '@/lib/modelGeometry';
import {cameraFrame} from '@/lib/modelCamera';
import {exteriorWall,floorFinish,interiorWall,surfaceTexture,photoTexture} from '@/lib/modelMaterials';
import {lightingFrame} from '@/lib/modelLighting';
import {furnitureCatalog,planRoomFurniture} from '@/lib/roomFurniturePlanner';
import type {FurniturePlacement} from '@/lib/roomFurniturePlanner';

type V3=[number,number,number];
function Box({position,size,color,rotation=[0,0,0],opacity=1,roughness=.72,metalness=0,texture=null,onClick}:{position:V3;size:V3;color:string;rotation?:V3;opacity?:number;roughness?:number;metalness?:number;texture?:Texture|null;onClick?:()=>void}){
 return <mesh position={position} rotation={rotation} castShadow receiveShadow onClick={onClick?e=>{e.stopPropagation();onClick()}:undefined}><boxGeometry args={size}/><meshStandardMaterial color={color} map={texture} transparent={opacity<1} opacity={opacity} roughness={roughness} metalness={metalness}/></mesh>;
}
function Cylinder({position,radius,height,color,rotation=[0,0,0]}:{position:V3;radius:number;height:number;color:string;rotation?:V3}){
 return <mesh position={position} rotation={rotation} castShadow receiveShadow><cylinderGeometry args={[radius,radius,height,24]}/><meshStandardMaterial color={color} roughness={.65}/></mesh>;
}
function FloorFinish({r,y,onClick,color,ceiling=false}:{r:Room;y:number;onClick?:()=>void;color?:string;ceiling?:boolean}){
 const geometry=useMemo(()=>roomFloorGeometry(r,y),[r,y]);
 useEffect(()=>()=>geometry.dispose(),[geometry]);
 const finish=floorFinish(r.type);
 return <mesh geometry={geometry} castShadow receiveShadow onClick={onClick?e=>{e.stopPropagation();onClick()}:undefined}><meshStandardMaterial side={ceiling?DoubleSide:FrontSide} color={color||finish.color} map={color?null:(photoTexture(finish.pattern)||surfaceTexture(finish.pattern))} normalMap={color?null:photoTexture(finish.pattern,'nor_gl')} roughnessMap={color?null:photoTexture(finish.pattern,'rough')} roughness={color ? .9 : finish.roughness} metalness={finish.metalness}/></mesh>;
}
function Furniture({layout,r,y}:{layout:Layout;r:Room;y:number}){
 const placements=useMemo(()=>planRoomFurniture(layout,r),[layout,r]);
 return <group>{placements.map(placement=><DetailedFurniture key={placement.id} placement={placement} y={y} unit={layout.unit}/>)}</group>;
}

function CameraRig({layout,floor}:{layout:Layout;floor:number}){
 const {size}=useThree();
 const frame=useMemo(()=>cameraFrame({...layout,width:layout.width+14,length:layout.length+14},floor,size.width,size.height,FLOOR_HEIGHT),[layout,floor,size.width,size.height]);
 return <><OrthographicCamera makeDefault position={frame.position} zoom={frame.zoom} near={.1} far={1500}/><OrbitControls makeDefault target={frame.target} enablePan enableRotate enableZoom minZoom={frame.zoom*.35} maxZoom={frame.zoom*4} maxPolarAngle={Math.PI/2.08}/></>;
}

export default function Model({layout,floor,onSelect,roof=false,showFurniture=true}:{layout:Layout;floor:number;onSelect:(id:string)=>void;roof?:boolean;showFurniture?:boolean}){
 const [resetViewKey,setResetViewKey]=useState(0),[fullHeight,setFullHeight]=useState(true),[garden,setGarden]=useState(true),[walk,setWalk]=useState(false);
 const house=useRef<Group>(null);
 async function exportScene(){if(!house.current)return;const model=house.current.clone(true);model.scale.multiplyScalar(.3048);model.position.multiplyScalar(.3048);const result=await new GLTFExporter().parseAsync(model,{binary:true});const url=URL.createObjectURL(new Blob([result as ArrayBuffer],{type:'model/gltf-binary'}));const a=document.createElement('a');a.href=url;a.download='archai-furnished-house.glb';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 const visible=(f:number)=>floor<0||f===floor;
 const light=lightingFrame(layout,FLOOR_HEIGHT);
 return <><Canvas shadows dpr={[1,1.25]} gl={{antialias:true,preserveDrawingBuffer:true,powerPreference:'high-performance',toneMapping:ACESFilmicToneMapping}}><color attach="background" args={['#dce3d9']}/>{walk?<Walkthrough layout={layout} floor={Math.max(0,floor)} onExit={()=>setWalk(false)}/>:<CameraRig key={resetViewKey} layout={layout} floor={floor}/>}<ambientLight intensity={.42}/><hemisphereLight intensity={.68} color="#fff7eb" groundColor="#79858a"/><directionalLight position={light.sunPosition} intensity={1.7} color="#fff4dd" castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-light.shadowExtent} shadow-camera-right={light.shadowExtent} shadow-camera-top={light.shadowExtent} shadow-camera-bottom={-light.shadowExtent} shadow-camera-far={light.shadowFar} shadow-normalBias={.025}/>
 <Suspense fallback={null}><Environment resolution={64} frames={1}><Lightformer intensity={2} position={[0,30,0]} rotation={[Math.PI/2,0,0]} scale={[80,80,1]}/><Lightformer intensity={1} position={[-30,10,-20]} scale={[40,25,1]}/></Environment></Suspense><group ref={house} position={[-layout.width/2,0,-layout.length/2]}>{garden&&<Garden layout={layout}/>}{layout.rooms.filter(r=>visible(r.floor)&&r.type!=='stair').map(r=>{const y=r.floor*FLOOR_HEIGHT;return <group key={r.id}><FloorFinish r={r} y={y} onClick={()=>onSelect(r.id)}/>{showFurniture&&<RoomDecor r={r} y={y}/>} {showFurniture&&<Furniture layout={layout} r={r} y={y}/>}</group>})}
 {layout.walls.filter(w=>visible(w.floor)).flatMap(w=>wallParts(layout,w).map(p=>({...p,bottom:Math.min(p.bottom,fullHeight||walk?9:4.8),top:Math.min(p.top,fullHeight||walk?9:4.8)})).filter(p=>p.top>p.bottom).map((p,i)=>{const transform=wallPartTransform(w,p),finish=w.exterior?exteriorWall:interiorWall;return <Box key={w.id+i} {...transform} color={finish.color} roughness={finish.roughness} metalness={finish.metalness} texture={surfaceTexture(finish.pattern)}/>;}))}
 {layout.doors.map(d=>{
  const w=layout.walls.find(v=>v.id===d.wall);if(!w||!visible(w.floor))return null;
  const base=Math.atan2(w.y2-w.y1,w.x2-w.x1),rotation:V3=[0,-base,0];
  const [hingeX,hingeZ]=wallPoint(w,d.position);
  if(d.kind==='vehicle'){
   const [cx,cz]=wallPoint(w,d.position+d.width/2);
   return <group key={d.id}>
    <Box position={[cx,w.floor*FLOOR_HEIGHT+4.55,cz]} size={[d.width,.28,.34]} rotation={rotation} color="#4c5c61" metalness={.2}/>
    <Box position={[cx,w.floor*FLOOR_HEIGHT+.05,cz]} size={[d.width,.08,.48]} rotation={rotation} color="#6f787a" metalness={.25}/>
    {[.2,.4,.6,.8].map(t=>{const [x,z]=wallPoint(w,d.position+d.width*t);return <Box key={t} position={[x,w.floor*FLOOR_HEIGHT+4.35,z]} size={[.07,.48,.38]} rotation={rotation} color="#829096"/>})}
   </group>;
  }
  const targetRoom=layout.rooms.find(r=>r.id===d.room_a);
  const nx=-Math.sin(base),nz=Math.cos(base),into=targetRoom?(targetRoom.x+targetRoom.width/2-hingeX)*nx+(targetRoom.y+targetRoom.height/2-hingeZ)*nz:1;
  // Door leaves stand open inside their room rather than across the common hall.
  const angle=base+(into>=0?Math.PI/2:-Math.PI/2);
  const cx=hingeX+Math.cos(angle)*d.width/2,cz=hingeZ+Math.sin(angle)*d.width/2;
  return <group key={d.id}>
   <Box position={[cx,w.floor*FLOOR_HEIGHT+3.5,cz]} size={[d.width,7,.18]} color="#8c6545" rotation={[0,-angle,0]}/>
   <Cylinder position={[hingeX+Math.cos(angle)*d.width*.85,w.floor*FLOOR_HEIGHT+2.4,hingeZ+Math.sin(angle)*d.width*.85]} radius={.09} height={.28} color="#c8a35d" rotation={[Math.PI/2,0,0]}/>
  </group>;
 })}
 {layout.windows.map(v=>{
  const w=layout.walls.find(q=>q.id===v.wall);if(!w||!visible(w.floor))return null;
  const [cx,cz]=wallPoint(w,v.position+v.width/2);
  const rotation:V3=[0,-Math.atan2(w.y2-w.y1,w.x2-w.x1),0];
  return <group key={v.id}>
   <Box position={[cx,w.floor*FLOOR_HEIGHT+5,cz]} size={[v.width,4,.08]} rotation={rotation} color="#8ec0cf" opacity={.32}/>
   {[3,7].map(height=><Box key={height} position={[cx,w.floor*FLOOR_HEIGHT+height,cz]} size={[v.width,.12,.14]} rotation={rotation} color="#34434a"/>)}
  </group>;
 })}
 {layout.stairs.filter(s=>visible(s.from_floor)||visible(s.to_floor)).flatMap(s=>stairParts(s).map((part,i)=><Box key={s.id+i} position={part.position} size={part.size} color="#b69a78"/>))}
 {walk&&layout.rooms.filter(r=>r.floor===Math.max(0,floor)&&!['stair','porch','parking','balcony','veranda'].includes(r.type)).map(r=><FloorFinish key={`ceiling-${r.id}`} r={r} y={r.floor*FLOOR_HEIGHT+9.1} color="#edece6" ceiling/>)}
 {roof&&layout.rooms.filter(r=>r.floor===layout.floors-1&&r.type!=='stair').map(r=><FloorFinish key={`roof-${r.id}`} r={r} y={layout.floors*FLOOR_HEIGHT-.5} color="#687383"/>)}</group>
 <ContactShadows position={[0,-.22,0]} opacity={.24} scale={light.contactScale} blur={3} far={light.contactFar}/></Canvas><div className="model-actions"><button className="button primary small" onClick={()=>setWalk(!walk)}>{walk?'Exit walkthrough':'Start walkthrough'}</button>{walk&&<span className="walk-help">Drag to look · WASD / arrows to walk · Esc to exit · Select a floor to visit it</span>}<button className="button secondary small" onClick={()=>setResetViewKey(value=>value+1)}>Reset camera</button><button className="button secondary small" onClick={()=>setFullHeight(!fullHeight)}>{fullHeight?'Cutaway walls':'Full-height walls'}</button><button className="button secondary small" onClick={()=>setGarden(!garden)}>{garden?'Hide garden':'Show garden'}</button><button className="button secondary small" onClick={()=>exportScene().catch(()=>alert('Model export failed. Try the geometry export menu.'))}>Download furnished GLB</button></div></>;
}

function Garden({layout}:{layout:Layout}){
 const w=layout.width,l=layout.length,access=siteAccess(layout);
 const fenceBox=(side:string,start:number,end:number,key:string)=>{
  const horizontal=side==='north'||side==='south',edge=side==='north'?-7:side==='south'?l+7:side==='west'?-7:w+7;
  return <Box key={key} position={horizontal?[(start+end)/2,1.5,edge]:[edge,1.5,(start+end)/2]} size={horizontal?[end-start,3,.25]:[.25,3,end-start]} color="#8b7658"/>;
 };
 return <group>
 <mesh position={[w/2,-.5,l/2]} receiveShadow><boxGeometry args={[w+16,.6,l+16]}/><meshStandardMaterial color="#6f8152" roughness={1}/></mesh>
 <Box position={[w/2,-.12,l/2]} size={[w+.9,.2,l+.9]} color="#bbb5a7"/>
 {(['north','south','east','west'] as const).flatMap(side=>side===access.side?access.fence.map(([a,b],i)=>fenceBox(side,a,b,side+i)):[fenceBox(side,-7,side==='north'||side==='south'?w+7:l+7,side)])}
 {access.gates.map((g,i)=>{
  const edge=access.side==='north'?-8:access.side==='south'?l+8:access.side==='west'?-8:w+8;
  const start=access.horizontal?g.z:g.x,depth=Math.abs(edge-start);
  return <Box key={'path'+i} position={access.horizontal?[g.x,-.08,(start+edge)/2]:[(start+edge)/2,-.08,g.z]} size={access.horizontal?[g.width,.12,depth]:[depth,.12,g.width]} color="#c6bba5"/>;
 })}
 {[-1,1].flatMap(side=>[.15,.55,.9].map((t,i)=>{
  const x=side<0?-4:w+4,z=l*t;
  // Leave driveways and pedestrian approaches free of trees.
  if(access.gates.some(g=>access.horizontal?Math.abs(x-g.x)<g.width/2+2:Math.abs(z-g.z)<g.width/2+2))return null;
  return <group key={`${side}-${i}`} position={[x,0,z]}><mesh position={[0,2.8,0]} castShadow><cylinderGeometry args={[.2,.35,5.6,8]}/><meshStandardMaterial color="#6c5237"/></mesh>{[0,1,2].map(n=><mesh key={n} position={[Math.sin(n*2.4)*1.3,5+n*.8,Math.cos(n*2.4)*1.3]} castShadow><sphereGeometry args={[2.2,12,10]}/><meshStandardMaterial color={n%2?'#536a3e':'#71824f'} roughness={.95}/></mesh>)}</group>;
 }))}
 </group>;
}

function RoomDecor({r,y}:{r:Room;y:number}){
 const cx=r.x+r.width/2,cz=r.y+r.height/2;
 return <group>
 {['living','bedroom'].includes(r.type)&&r.width>9&&r.height>9&&<Box position={[cx,y+.22,cz]} size={[Math.min(8,r.width*.55),.04,Math.min(6,r.height*.45)]} color={r.type==='living'?'#b6b3a2':'#d6c9b9'} roughness={.96}/>}
 {r.type==='bedroom'&&r.width>10&&<><Box position={[r.x+1.2,y+.8,r.y+1.2]} size={[1.2,1.6,1.2]} color="#99734f"/><Cylinder position={[r.x+1.2,y+2.05,r.y+1.2]} radius={.35} height={.65} color="#e9ddc7"/></>}
 </group>;
}
