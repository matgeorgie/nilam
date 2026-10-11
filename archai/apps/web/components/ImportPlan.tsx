'use client';
import {useState} from 'react';
import {api} from '@/lib/api';
import type {Layout} from '@/lib/types';
export default function ImportPlan({onImport,onClose}:{onImport:(layout:Layout)=>void;onClose:()=>void}){
 const [file,setFile]=useState<File|null>(null),[width,setWidth]=useState(40),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function convert(){if(!file)return;setBusy(true);setError('');try{
  if(file.name.endsWith('.json')){const parsed=JSON.parse(await file.text());const layout=parsed.layout||parsed;if(!Array.isArray(layout.rooms)||!Array.isArray(layout.walls)||!(layout.width>0)||!(layout.length>0))throw new Error('Choose an ArchAI layout JSON.');const result=await api<{layout:Layout}>('/reconstruct-plan/geometry',{method:'POST',body:JSON.stringify(layout)});onImport(result.layout);onClose();return;}
  if(file.size>8000000)throw new Error('Choose an image smaller than 8 MB.');
  const encoded=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsDataURL(file)});
  const result=await api<{layout:Layout}>('/reconstruct-plan',{method:'POST',body:JSON.stringify({image_base64:encoded,image_width_feet:width})});onImport(result.layout);onClose();
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title"><button className="icon-button close" onClick={onClose} disabled={busy} aria-label="Close import">?</button><span className="eyebrow">FROM DRAWING TO SPACE</span><h2 id="import-title">Convert a 2D plan to 3D</h2><p>Upload a clean PNG/JPEG floor plan for local AI analysis, or an ArchAI layout JSON for exact reconstruction.</p><input aria-label="Choose floor plan" type="file" accept=".png,.jpg,.jpeg,.json" onChange={e=>setFile(e.target.files?.[0]||null)}/><label className="import-width">Total image width in feet<input aria-label="Image width in feet" type="number" min={1} max={1000} value={width} onChange={e=>setWidth(Number(e.target.value))}/></label><p className="muted">Crop white margins before measuring the image width. Image imports are inferred drafts: review wall positions, room labels and openings. Best with orthogonal plans.</p>{error&&<p className="error" role="alert">{error}</p>}<button className="button primary" disabled={!file||busy||!(width>0)} onClick={convert}>{busy?'Analysing floor plan?':'Build 3D from this plan'}</button></section></div>;
}
