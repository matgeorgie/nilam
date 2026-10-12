'use client';

import {use, useEffect, useState} from 'react';
import Link from 'next/link';
import {ArrowLeft, ArrowRight, Building2, Calculator, CheckCircle2, ExternalLink, MapPin, Printer, RefreshCw} from 'lucide-react';
import {api} from '@/lib/api';
import type {CostEstimate, Project} from '@/lib/types';
import './estimate.css';

const districts = ['Kasaragod','Kannur','Wayanad','Kozhikode','Malappuram','Palakkad','Thrissur','Ernakulam','Idukki','Kottayam','Alappuzha','Pathanamthitta','Kollam','Thiruvananthapuram'];
const finishes = [
  {id:'essential', name:'Essential', description:'Practical materials and restrained fittings'},
  {id:'standard', name:'Standard', description:'Durable everyday finishes and fixtures'},
  {id:'premium', name:'Premium', description:'Higher-spec finishes and detailing'},
] as const;
const money = (value:number) => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(value);
const compactMoney = (value:number) => value>=10_000_000 ? `₹${(value/10_000_000).toFixed(2)} cr` : `₹${(value/100_000).toFixed(1)} lakh`;

export default function CostPage({params}:{params:Promise<{id:string}>}) {
  const {id}=use(params);
  const [project,setProject]=useState<Project|null>(null);
  const [estimate,setEstimate]=useState<CostEstimate|null>(null);
  const [finish,setFinish]=useState<CostEstimate['finish']>('standard');
  const [district,setDistrict]=useState('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');

  useEffect(()=>{
    let active=true;
    api<Project>(`/projects/${id}`).then(value=>{
      if(!active)return;
      setProject(value);
      const region=value.specification.site_context?.district;
      setDistrict(region&&districts.includes(region)?region:'');
      setLoading(false);
    }).catch(reason=>{if(active){setError((reason as Error).message);setLoading(false)}});
    return()=>{active=false};
  },[id]);

  useEffect(()=>{
    if(!project?.current_revision)return;
    let active=true;
    setLoading(true);
    setError('');
    const search=new URLSearchParams({finish});
    if(district)search.set('district',district);
    api<CostEstimate>(`/projects/${id}/estimate?${search}`).then(value=>{if(active){setEstimate(value);setLoading(false)}})
      .catch(reason=>{if(active){setError((reason as Error).message);setLoading(false)}});
    return()=>{active=false};
  },[project?.current_revision,finish,district,id]);

  return <main className="cost-page">
    <header className="cost-topbar"><Link href={`/workspace/${id}`} className="cost-back"><ArrowLeft size={18}/> Back to design</Link><span className="cost-brand"><span className="cost-brand-mark">N</span> NILAM <i/> ArchAI</span><button className="cost-print" onClick={()=>window.print()} disabled={!estimate}><Printer size={16}/> Print estimate</button></header>
    <div className="cost-shell">
      <div className="cost-intro"><div><span className="cost-eyebrow"><Calculator size={14}/> FROM DESIGN TO BUDGET</span><h1>What could this home cost?</h1><p>A Kerala planning estimate drawn from your saved floor plan, selected finish and regional construction inputs.</p></div><div className="cost-project"><Building2 size={18}/><div><small>CURRENT DESIGN</small><strong>{project?.name||'Loading design…'}</strong><span>{project?.layout?.floors||'—'} floor{project?.layout?.floors===1?'':'s'} · {project?.layout?.rooms.length||'—'} mapped spaces</span></div></div></div>
      {error&&<div role="alert" className="cost-error">{error}<button onClick={()=>window.location.reload()}><RefreshCw size={14}/> Retry</button></div>}
      {!loading&&project&&!project.layout&&<div className="cost-empty"><Calculator size={35}/><h2>Start with a finished floor plan</h2><p>The budget will appear as soon as a design is saved.</p><Link href={`/workspace/${id}`}>Continue designing <ArrowRight size={15}/></Link></div>}
      {project?.layout&&<>
        <section className="cost-controls" aria-label="Estimate assumptions"><div className="cost-control-heading"><span className="cost-step">01</span><div><h2>Set the scope</h2><p>Your Nilam district is selected automatically. You can compare another Kerala district or finish.</p></div></div><div className="cost-controls-grid"><label className="cost-region"><span><MapPin size={15}/> CONSTRUCTION DISTRICT</span><select value={district} onChange={event=>setDistrict(event.target.value)}><option value="">Kerala statewide average</option>{districts.map(name=><option key={name} value={name}>{name}</option>)}</select><small>{district&&district===project.specification.site_context?.district?'Carried from your Nilam site':'Used for a regional input-price adjustment'}</small></label><div className="cost-finish"><span>FINISH LEVEL</span><div role="group" aria-label="Finish level" className="cost-finish-options">{finishes.map(option=><button key={option.id} type="button" className={finish===option.id?'selected':''} aria-pressed={finish===option.id} onClick={()=>setFinish(option.id)}><strong>{option.name}</strong><small>{option.description}</small></button>)}</div></div></div></section>
        {estimate?<div className={`cost-result ${loading?'updating':''}`} aria-busy={loading}><section className="cost-hero"><div><span className="cost-kicker">PLANNING BUDGET · {estimate.district||'KERALA AVERAGE'}</span><div className="cost-big-number">{compactMoney(estimate.planning_budget_inr)}</div><p>Estimated construction plus a 12% planning reserve</p><div className="cost-range"><span>Indicative planning range</span><strong>{compactMoney(estimate.planning_range_inr.low)} – {compactMoney(estimate.planning_range_inr.high)}</strong></div></div><div className="cost-area-card"><span>DESIGN-MEASURED AREA</span><strong>{estimate.area.gross_enclosed_sqft.toLocaleString('en-IN')} <small>sq ft</small></strong><p>enclosed gross area, across {estimate.floors.length} floor{estimate.floors.length===1?'':'s'}</p><div><span>{estimate.area.semi_open_sqft.toLocaleString('en-IN')} sq ft</span> semi-open space</div><div><span>{estimate.requirements.bathrooms}</span> bathroom{estimate.requirements.bathrooms===1?'':'s'} · <span>{estimate.requirements.kitchens}</span> kitchen{estimate.requirements.kitchens===1?'':'s'}</div></div></section>
          <section className="cost-breakdown"><div className="cost-section-title"><span className="cost-step">02</span><div><h2>Where the number comes from</h2><p>Each amount is tied to the geometry and requirements in the current saved design.</p></div></div><div className="cost-table"><div className="cost-table-header"><span>SCOPE</span><span>ESTIMATE</span></div>{estimate.line_items.filter(item=>item.amount_inr>0).map(item=><div className="cost-line" key={item.label}><div><strong>{item.label}</strong><small>{item.detail}</small></div><strong>{money(item.amount_inr)}</strong></div>)}<div className="cost-line cost-subtotal"><strong>Estimated construction</strong><strong>{money(estimate.construction_inr)}</strong></div><div className="cost-line"><div><strong>Planning reserve</strong><small>12% for normal estimate uncertainty</small></div><strong>{money(estimate.reserve_inr)}</strong></div><div className="cost-line cost-total"><strong>Planning budget</strong><strong>{money(estimate.planning_budget_inr)}</strong></div></div></section>
          <section className="cost-detail-grid"><div className="cost-detail-card"><div className="cost-section-title"><span className="cost-step">03</span><div><h2>Plan measurements</h2><p>Measured room polygons are combined by floor, so overlapping spaces are not double-counted.</p></div></div><div className="cost-floor-table">{estimate.floors.map(floor=><div key={floor.floor}><strong>{floor.floor===0?'Ground floor':floor.floor===1?'First floor':`Floor ${floor.floor}`}</strong><span>{floor.gross_enclosed_sqft.toLocaleString('en-IN')} sq ft enclosed</span><small>{floor.semi_open_sqft.toLocaleString('en-IN')} sq ft semi-open</small></div>)}</div><div className="cost-measure-note"><CheckCircle2 size={16}/> The estimate adds {estimate.area.wall_allowance_sqft.toLocaleString('en-IN')} sq ft for walls within the saved footprint. Porches, balconies and parking count at 45% of the rate.</div></div><div className="cost-detail-card"><div className="cost-section-title"><span className="cost-step">04</span><div><h2>Local rate basis</h2><p>Regional material and wage observations tune a broad residential construction band.</p></div></div><div className="cost-metric"><span>Selected finish band</span><strong>{money(estimate.rate_band_inr_sqft.low)}–{money(estimate.rate_band_inr_sqft.high)} <small>/ sq ft</small></strong></div><div className="cost-metric"><span>District input adjustment</span><strong>{Math.abs(estimate.district_factor-1)<.005?'Near Kerala average':`${estimate.district_factor>1?'+':''}${((estimate.district_factor-1)*100).toFixed(1)}%`}</strong></div><p className="cost-fineprint">The district adjustment is a capped proxy from reported cement, steel, blocks and labour prices. It is not a contractor quote.</p></div></section>
          <section className="cost-notes"><div><h2>What to know before building</h2><p>{estimate.method}</p><h3>Included in the planning method</h3><ul>{estimate.assumptions.map(value=><li key={value}>{value}</li>)}</ul><h3>Needs separate pricing</h3><ul>{estimate.exclusions.map(value=><li key={value}>{value}</li>)}</ul></div><div className="cost-sources"><span>RATE REFERENCES</span>{estimate.sources.map(source=><a href={source.url} target="_blank" rel="noopener noreferrer" key={source.url}><strong>{source.title}</strong><small>{source.use}</small><ExternalLink size={15}/></a>)}<Link href={`/workspace/${id}`}>Refine the design <ArrowRight size={16}/></Link></div></section>
        </div>:<div className="cost-loading">{loading?'Measuring the saved plan and applying Kerala rates…':'Estimate unavailable.'}</div>}
      </>}
    </div>
  </main>;
}
