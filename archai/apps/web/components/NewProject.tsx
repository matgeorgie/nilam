'use client';
import {useEffect,useRef,useState} from 'react';
import FloorRequirements,{floorName} from './FloorRequirements';
import {X,ArrowRight,ArrowLeft,House,Check,LayoutGrid,Sparkles,MapPin} from 'lucide-react';
import {api} from '@/lib/api';
import {DESIGN_BASE} from '@/lib/nilam';
import {HouseShape,type Project,type Specification,type RoomRequirement,type SiteContext} from '@/lib/types';
const footprints=[[HouseShape.RECTANGLE,'Rectangle'],[HouseShape.AUTO,'Best fit'],[HouseShape.L_SHAPE,'L shape'],[HouseShape.T_SHAPE,'T shape'],[HouseShape.U_SHAPE,'U shape'],[HouseShape.C_SHAPE,'C shape'],[HouseShape.STEPPED,'Stepped'],[HouseShape.COURTYARD,'Courtyard']] as const;
function room(type:string,floor:number,name?:string,attached=false):RoomRequirement{return {type,name:name||`${type[0].toUpperCase()+type.slice(1)} · ${floorName(floor)}`,count:1,preferred_floor:floor,attached_bathroom:attached}}
function starter():RoomRequirement[]{return [room('bedroom',0,'Ground bedroom 1'),room('bedroom',0,'Ground bedroom 2'),...['living','dining','kitchen','bathroom'].map(k=>room(k,0))]}
export default function NewProject({onClose,siteContext=null,embedded=false}:{onClose:()=>void;siteContext?:SiteContext|null;embedded?:boolean}){
 const [step,setStep]=useState(0),[name,setName]=useState('My new home');
 const [width,setWidth]=useState(30),[length,setLength]=useState(40),[unit,setUnit]=useState<'feet'|'meters'>('feet'),[road,setRoad]=useState('south'),[shape,setShape]=useState<HouseShape>(HouseShape.RECTANGLE),[floors,setFloors]=useState(1);
 const [front,setFront]=useState(0),[rear,setRear]=useState(0),[left,setLeft]=useState(0),[right,setRight]=useState(0),[orientation,setOrientation]=useState('north'),[plotPolygon,setPlotPolygon]=useState('');
 const [rooms,setRooms]=useState<RoomRequirement[]>(starter),[parking,setParking]=useState(0),[preferences,setPreferences]=useState<Specification['preferences']>({open_kitchen:true});
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[elapsed,setElapsed]=useState(0),[furthest,setFurthest]=useState(0);
 const projectId=useRef<string|null>(null),content=useRef<HTMLDivElement>(null),heading=useRef<HTMLHeadingElement>(null),modal=useRef<HTMLElement>(null),errorBox=useRef<HTMLDivElement>(null);
 const review=step===floors+2,roomStep=step>=2&&!review,activeFloor=step-2;
 useEffect(()=>{content.current?.scrollTo({top:0});if(!embedded)heading.current?.focus()},[step,embedded]);
 useEffect(()=>{if(error){errorBox.current?.focus();errorBox.current?.scrollIntoView({block:'nearest'})}},[error]);
 useEffect(()=>{if(embedded)return;const previous=document.activeElement as HTMLElement,overflow=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{document.body.style.overflow=overflow;previous?.focus()}},[embedded]);
 useEffect(()=>{
  function keyboard(event:KeyboardEvent){
   if(embedded)return;
   if(event.key==='Escape'&&!busy){event.preventDefault();onClose();return}
   if(event.key!=='Tab')return;
   const nodes=Array.from(modal.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]')||[]).filter(e=>e.getClientRects().length>0);
   const first=nodes[0],last=nodes[nodes.length-1];
   if(event.shiftKey&&(document.activeElement===first||document.activeElement===heading.current)){event.preventDefault();last?.focus()}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
  }
  document.addEventListener('keydown',keyboard);return()=>document.removeEventListener('keydown',keyboard);
 },[busy,onClose,embedded]);
 useEffect(()=>{if(!busy){setElapsed(0);return}const id=setInterval(()=>setElapsed(n=>n+1),1000);return()=>clearInterval(id)},[busy]);
 function specification(validate=false):Specification{
  const polygon=plotPolygon.trim()?plotPolygon.split(';').map(p=>p.trim().split(',').map(Number) as [number,number]):null;
  if(validate){
   if(!name.trim())throw new Error('Give your project a name.');
   if(!Number.isFinite(width)||!Number.isFinite(length)||width<=0||length<=0)throw new Error('Enter a positive plot width and length.');
   if([front,rear,left,right].some(n=>!Number.isFinite(n)||n<0)||front+rear>=length||left+right>=width)throw new Error('Setbacks must leave space inside the plot. Reduce them or check the plot dimensions.');
   if(polygon&&(polygon.length<3||polygon.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v)))))throw new Error('Enter at least three polygon points as x,y pairs separated by semicolons.');
  }
  return {plot_width:width,plot_length:length,plot_polygon:polygon,shape,shape_parameters:{},setbacks:{front_setback:front,rear_setback:rear,left_setback:left,right_setback:right},unit,floors,orientation,north_angle:0,road_location:road,road_width:null,rooms:rooms.filter(r=>(r.preferred_floor??0)<floors),parking_spaces:parking,style:null,special_requirements:[],preferences,relationships:[],site_context:siteContext,provenance:{plot_width:'user',plot_length:'user',plot_polygon:polygon?'user':'system_default',shape:'user',floors:'user',road_location:'user',setbacks:'user',orientation:'user'}};
 }
 function change(spec:Specification){setRooms(spec.rooms);setParking(spec.parking_spaces);setPreferences(spec.preferences);setError('')}
 function go(next:number){setError('');setStep(next);setFurthest(n=>Math.max(n,next))}
 function continueStep(){
  try{if(step===0)specification(true);if(roomStep&&!rooms.some(r=>(r.preferred_floor??0)===activeFloor&&r.count>0))throw new Error(`Choose at least one room for the ${floorName(activeFloor).toLowerCase()}.`);go(step+1)}catch(e){setError((e as Error).message)}
 }
 function template(duplex:boolean){
  setUnit('feet');setWidth(duplex?50:30);setLength(duplex?60:40);setShape(HouseShape.RECTANGLE);setPlotPolygon('');setFront(0);setRear(0);setLeft(0);setRight(0);setFloors(duplex?2:1);setParking(duplex?1:0);setPreferences({open_kitchen:true});setRooms(duplex?[...['living','dining','kitchen','utility','bedroom','bathroom','porch'].map(k=>room(k,0)),room('bedroom',1,'Master bedroom',true),room('bedroom',1,'Second bedroom'),room('living',1,'Family lounge'),room('bathroom',1,'Upper shared bathroom'),room('balcony',1,'Balcony')]:starter());setFurthest(1);go(1);
 }
 async function create(){
  setError('');
  try{
   const spec=specification(true);
   for(let f=0;f<floors;f++)if(!spec.rooms.some(r=>(r.preferred_floor??0)===f&&r.count>0))throw new Error(`Add rooms to the ${floorName(f).toLowerCase()} before generating.`);
   setBusy(true);
   if(projectId.current){await api('/projects/'+projectId.current,{method:'PATCH',body:JSON.stringify({name:name.trim()})});await api('/projects/'+projectId.current+'/requirements',{method:'POST',body:JSON.stringify({specification:spec})})}
   else {const p=await api<Project>('/projects',{method:'POST',body:JSON.stringify({name:name.trim(),specification:spec})});projectId.current=p.id;await api('/projects/'+p.id+'/generate',{method:'POST'})}
   location.href=DESIGN_BASE+'/workspace/'+projectId.current;
  }catch(e){setError((e as Error).message);setBusy(false)}
 }
 const title=step===0?'Tell us about your plot.':step===1?'How many floors do you need?':review?'Does this look right?':`What goes on the ${floorName(activeFloor).toLowerCase()}?`;
 const stage=step<2?step:review?3:2;
 const totalBedrooms=rooms.filter(r=>r.type==='bedroom'&&(r.preferred_floor??0)<floors).reduce((n,r)=>n+r.count,0);
 return <div className={embedded?'embedded-wizard-wrap':'modal-backdrop'}><section ref={modal} className="modal wizard brief-wizard" role={embedded?undefined:'dialog'} aria-modal={embedded?undefined:true} aria-labelledby="wizard-title">
 <header className="brief-header"><div className="brief-brand"><House size={20}/><span>Build your home brief</span></div><button className="icon-button" aria-label="Close new project" disabled={busy} onClick={onClose}><X size={19}/></button><nav className="brief-progress" aria-label="Design steps">{['Plot','Floors','Rooms','Review'].map((label,i)=>{const target=i<2?i:i===2?2:floors+2;return <button type="button" key={label} disabled={busy||target>furthest} aria-current={stage===i?'step':undefined} onClick={()=>go(target)}><b>{i<stage?<Check size={13}/>:i+1}</b>{label}</button>})}</nav></header>
 <div className="brief-content" ref={content}><h2 id="wizard-title" ref={heading} tabIndex={-1}>{title}</h2><p className="brief-subtitle">{step===0?'Enter the actual plot measurements and road side. The selected map point is a location reference, not a measured parcel.':step===1?'Ground floor is the first level. You’ll choose rooms for each level next.':review?'These are the exact room requirements we’ll send to the planner. Change anything before generating.':'Use + and − to choose rooms. Private bathrooms belong to the bedrooms you select.'}</p>
 {siteContext&&step===0&&<div className="brief-site-reference"><MapPin size={17}/><div><strong>{siteContext.district} site selected in Nilam</strong><span>{siteContext.lat.toFixed(5)}, {siteContext.lon.toFixed(5)} · Location reference only</span></div></div>}
 {step===0?<>
 <label>Project name<input value={name} onChange={e=>setName(e.target.value)} maxLength={100}/></label>
 <div className="site-dimensions"><label>Plot width<input type="number" min={1} max={300} value={width} onChange={e=>setWidth(Number(e.target.value))}/></label><span>×</span><label>Plot length<input type="number" min={1} max={300} value={length} onChange={e=>setLength(Number(e.target.value))}/></label><label>Units<select value={unit} onChange={e=>setUnit(e.target.value as 'feet'|'meters')}><option value="feet">Feet</option><option value="meters">Meters</option></select></label></div>
 <section className="road-question"><div><h3>Which side has the road?</h3><p>This sets the entrance and parking approach.</p></div><div className="road-picker">{['north','west','east','south'].map(side=><button type="button" className={`road-${side}`} key={side} aria-label={`Road on ${side}`} aria-pressed={road===side} onClick={()=>setRoad(side)}>{side[0].toUpperCase()+side.slice(1)}</button>)}<span className="road-plot"><House size={24}/><small>Your plot</small></span></div></section>
 <details className="brief-advanced"><summary>Setbacks, footprint & irregular plots</summary><p className="muted">Optional site constraints. Rectangle is the most reliable footprint; other shapes are experimental.</p><div className="shape-options brief-shapes">{footprints.map(([id,label])=><button type="button" key={id} aria-label={`${label} footprint`} aria-pressed={shape===id} className={shape===id?'selected':''} onClick={()=>setShape(id)}><LayoutGrid size={20}/>{label}</button>)}</div><div className="form-grid">{[['Front setback',front,setFront],['Rear setback',rear,setRear],['Left setback',left,setLeft],['Right setback',right,setRight]].map(([label,value,setter])=><label key={label as string}>{label as string}<input type="number" min={0} step={.5} value={value as number} onChange={e=>(setter as (n:number)=>void)(Number(e.target.value))}/></label>)}<label>North orientation<select value={orientation} onChange={e=>setOrientation(e.target.value)}>{['north','south','east','west'].map(x=><option key={x}>{x}</option>)}</select></label></div><label>Optional plot polygon<textarea rows={2} value={plotPolygon} onChange={e=>setPlotPolygon(e.target.value)} placeholder="0,0; 30,0; 28,50; 0,50"/></label><small>Coordinates use the selected units. Leave blank for a rectangular plot.</small></details>
 <details className="brief-advanced"><summary>Prefer a ready-made starting brief?</summary><p>These examples replace your current plot and room choices. You can change every answer next.</p><div className="starter-choices"><button type="button" onClick={()=>template(false)}><strong>Compact home</strong><small>30 × 40 ft · 1 floor · 2 bedrooms</small></button><button type="button" onClick={()=>template(true)}><strong>Family duplex</strong><small>50 × 60 ft · 2 floors · 3 bedrooms</small></button></div></details>
 </>:step===1?<><div className="floor-choices">{[1,2,3,4].map(n=><button type="button" key={n} aria-label={`${n} ${n===1?'floor':'floors'}`} aria-pressed={floors===n} onClick={()=>{setFloors(n);setFurthest(1)}}><span className="floor-stack">{Array.from({length:n},(_,i)=><i key={i}/>)}</span><strong>{n} {n===1?'floor':'floors'}</strong><small>{n===1?'Ground floor only':`Ground + ${n-1} upper ${n===2?'floor':'floors'}`}</small></button>)}</div><p className="info-note">A stairwell and landings will be reserved when your home has more than one floor.</p></>:roomStep?<><div className="floor-tabs">{Array.from({length:floors},(_,f)=><button key={f} type="button" aria-pressed={f===activeFloor} disabled={2+f>furthest} onClick={()=>go(2+f)}>{floorName(f)}</button>)}</div><FloorRequirements value={specification()} onChange={change} fixedFloor={activeFloor} showSummary={false}/></>:<>
 <section className="brief-review-site"><div><strong>{name}</strong><p>{width} × {length} {unit} · {floors} {floors===1?'floor':'floors'} · road on {road} · {shape.replaceAll('_',' ')}</p><small>{parking} car parking {parking===1?'space':'spaces'} · {preferences.open_kitchen!==false?'Open':'Closed'} kitchen</small></div><button type="button" onClick={()=>go(0)}>Change plot</button><button type="button" onClick={()=>go(1)}>Change floors</button></section>
 {Array.from({length:floors},(_,f)=>{const rr=rooms.filter(r=>(r.preferred_floor??0)===f);const attached=rr.filter(r=>r.type==='bedroom'&&r.attached_bathroom).reduce((n,r)=>n+r.count,0);return <section className="brief-floor-summary" key={f}><div><h3>{floorName(f)}</h3><button type="button" aria-label={`Change ${floorName(f)} rooms`} onClick={()=>go(2+f)}>Change rooms</button></div><div className="review-room-tags">{rr.map((r,i)=><span key={i}>{r.type==='bedroom'?r.name:`${r.count} ${r.type==='living'&&f>0?'family lounge':r.type}${r.count>1?'s':''}`}{r.attached_bathroom?' + attached bathroom':''}</span>)}</div><small>{attached} attached {attached===1?'bathroom':'bathrooms'}{f===0?` · ${parking} parking spaces`:''}</small>{rr.some(r=>r.type==='bedroom')&&!attached&&!rr.some(r=>r.type==='bathroom')&&<p className="review-warning">No bathroom on this floor. Consider adding a shared bathroom or attaching one to a bedroom.</p>}</section>})}
 <p className="brief-ai-note"><Sparkles size={17}/> After generation, use local AI chat to request design changes. Room counts above are confirmed choices, so they don’t need AI interpretation.</p>
 </>}
 {error&&<div ref={errorBox} tabIndex={-1} className="brief-error" role="alert"><strong>{review?'We couldn’t generate this design yet.':'Please check this answer.'}</strong>{review?<><p>Your choices are kept. The current planner may not support this combination. Review rooms or plot settings and try again.</p><details><summary>Show planner details</summary><p>{error}</p></details><div><button type="button" onClick={()=>go(2)}>Review rooms</button><button type="button" onClick={()=>go(0)}>Edit plot</button></div></>:<p>{error}</p>}</div>}
 </div>
 <footer className="brief-footer"><div className="brief-live-summary">{width} × {length} {unit} · {floors} {floors===1?'floor':'floors'} · {totalBedrooms} bedrooms</div><div className="modal-actions"><button className="button secondary" onClick={()=>step?go(step-1):onClose()} disabled={busy}><ArrowLeft size={16}/>{step?'Back':'Cancel'}</button><button className="button primary" disabled={busy} onClick={()=>review?create():continueStep()}>{busy?'Creating your plan…':review?'Generate 2D plan':roomStep&&activeFloor<floors-1?`Next: ${floorName(activeFloor+1).toLowerCase()}`:roomStep?'Review my brief':'Continue'}{review?<Sparkles size={17}/>:<ArrowRight size={17}/>}</button></div>{busy&&<p role="status" aria-live="polite" className="generation-progress">Checking layouts and stair access… {elapsed}s. Your answers are saved in this session.</p>}</footer>
 </section></div>;
}
