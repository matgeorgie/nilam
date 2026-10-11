'use client';
import {useState} from 'react';
import {BedDouble,CookingPot,Sofa,Plus,Minus} from 'lucide-react';
import type {Specification,RoomRequirement} from '@/lib/types';
export const floorName=(floor:number)=>['Ground floor','First floor','Second floor','Third floor'][floor]||`Floor ${floor}`;
const extras=[['utility','Utility / laundry'],['office','Study / office'],['porch','Entrance sit-out'],['balcony','Balcony']] as const;
export function RoomCounter({label,hint,value,onChange,ariaLabel,max=8}:{label:string;hint?:string;value:number;onChange:(n:number)=>void;ariaLabel:string;max?:number}){
 return <div className="room-counter"><div><strong>{label}</strong>{hint&&<small>{hint}</small>}</div><div className="counter-controls"><button type="button" aria-label={`Decrease ${ariaLabel}`} disabled={value<=0} onClick={()=>onChange(value-1)}><Minus size={16}/></button><input aria-label={ariaLabel} type="number" min={0} max={max} value={value} onChange={e=>onChange(Math.max(0,Math.min(max,Math.trunc(Number(e.target.value))||0)))}/><button type="button" aria-label={`Increase ${ariaLabel}`} disabled={value>=max} onClick={()=>onChange(value+1)}><Plus size={16}/></button></div></div>;
}
export default function FloorRequirements({value,onChange,fixedFloor,showSummary=true}:{value:Specification;onChange:(value:Specification)=>void;fixedFloor?:number;showSummary?:boolean}){
 const [active,setActive]=useState(0),floor=fixedFloor??Math.min(active,(value.floors||1)-1);
 const rooms=value.rooms.filter(r=>(r.preferred_floor??0)===floor);
 const bedrooms=rooms.filter(r=>r.type==='bedroom');
 function count(type:string){return rooms.filter(r=>r.type===type).reduce((n,r)=>n+r.count,0)}
 function setCount(type:string,n:number){
  n=Math.max(0,Math.min(8,Math.trunc(n)||0));
  const other=value.rooms.filter(r=>!((r.preferred_floor??0)===floor&&r.type===type));
  const existing=rooms.filter(r=>r.type===type);
  const next:RoomRequirement[]=type==='bedroom'?Array.from({length:n},(_,i)=>({...existing[i],type,name:existing[i]?.name||`${floorName(floor)} bedroom ${i+1}`,count:1,preferred_floor:floor,attached_bathroom:existing[i]?.attached_bathroom||false})):n?[{...existing[0],type,name:existing[0]?.name||`${type[0].toUpperCase()+type.slice(1)} floor ${floor}`,count:n,preferred_floor:floor,attached_bathroom:false}]:[];
  onChange({...value,rooms:[...other,...next],spatial_intent:undefined} as Specification);
 }
 return <div className="guided-requirements room-builder">
 {fixedFloor==null&&<div className="floor-tabs" aria-label="Choose floor">{Array.from({length:value.floors||1},(_,i)=><button type="button" key={i} aria-pressed={i===floor} onClick={()=>setActive(i)}>{floorName(i)}</button>)}</div>}
 <section className="room-group"><h3><BedDouble size={19}/> Bedrooms & bathrooms</h3>
 <RoomCounter label="Bedrooms" hint="Each bedroom can have its own bathroom below." value={count('bedroom')} onChange={n=>setCount('bedroom',n)} ariaLabel={`Bedrooms floor ${floor}`}/>
 {bedrooms.length>0&&<div className="ensuite-list"><p>Which bedrooms need a private bathroom?</p>{bedrooms.map((r,i)=><label key={i} className="ensuite-option"><span><strong>{r.name}</strong></span><span><input aria-label={`Attached bathroom bedroom ${i+1} floor ${floor}`} type="checkbox" checked={r.attached_bathroom} onChange={e=>onChange({...value,rooms:value.rooms.map(x=>x===r?{...x,attached_bathroom:e.target.checked}:x)})}/> Attached bathroom</span></label>)}</div>}
 <RoomCounter label="Shared bathrooms" hint="Accessible from the hall; separate from attached bathrooms." value={count('bathroom')} onChange={n=>setCount('bathroom',n)} ariaLabel={`Shared bathrooms floor ${floor}`}/>
 </section>
 <section className="room-group"><h3><Sofa size={19}/> Living & cooking</h3>
 <RoomCounter label={floor===0?'Living rooms':'Family lounges / living rooms'} value={count('living')} onChange={n=>setCount('living',n)} ariaLabel={`Living rooms / family lounges floor ${floor}`}/>
 <RoomCounter label="Dining areas" value={count('dining')} onChange={n=>setCount('dining',n)} ariaLabel={`Dining areas floor ${floor}`}/>
 <RoomCounter label="Kitchens" value={count('kitchen')} onChange={n=>setCount('kitchen',n)} ariaLabel={`Kitchens floor ${floor}`}/>
 {count('kitchen')>0&&<label className="kitchen-choice"><CookingPot size={17}/><input aria-label="Open kitchen" type="checkbox" checked={value.preferences.open_kitchen!==false} onChange={e=>onChange({...value,preferences:{...value.preferences,open_kitchen:e.target.checked}})}/> Open kitchen connected to dining<small>Applies to the whole house</small></label>}
 </section>
 <section className="room-group"><h3><Plus size={19}/> Add other spaces</h3><p className="group-help">Optional. Tap a space to add it.</p><div className="extra-rooms">{extras.map(([type,label])=>count(type)>0?<RoomCounter key={type} label={label} value={count(type)} onChange={n=>setCount(type,n)} ariaLabel={`${label} floor ${floor}`}/>:<button type="button" key={type} onClick={()=>setCount(type,1)}><Plus size={15}/>{label}</button>)}</div>
 {floor===0&&<RoomCounter label="Car parking spaces" hint="Vehicle access will follow the road side you chose." value={value.parking_spaces} onChange={n=>onChange({...value,parking_spaces:n})} ariaLabel="Car parking spaces" max={4}/>}
 </section>
 {showSummary&&<div className="info-note">{Array.from({length:value.floors||1},(_,i)=>{const rr=value.rooms.filter(r=>(r.preferred_floor??0)===i);return <div key={i}><strong>{floorName(i)}: </strong>{rr.map(r=>`${r.count} ${r.type}${r.attached_bathroom?' + attached bathroom':''}`).join(', ')||'No rooms selected'}</div>})}</div>}
 </div>;
}
