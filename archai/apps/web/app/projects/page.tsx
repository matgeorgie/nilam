'use client';
import {useEffect,useState} from 'react';
import {ArrowLeft,ArrowUpRight,Copy,FolderOpen,MapPin,Plus,Search,Trash2} from 'lucide-react';
import Brand from '@/components/Brand';
import Plan from '@/components/Plan';
import {api} from '@/lib/api';
import {DESIGN_BASE,NILAM_URL} from '@/lib/nilam';
import type {Project} from '@/lib/types';

export default function Projects(){
 const [projects,setProjects]=useState<Project[]>([]),[query,setQuery]=useState(''),[error,setError]=useState(''),[loaded,setLoaded]=useState(false);
 async function load(){try{setProjects(await api<Project[]>('/projects'));setLoaded(true)}catch(e){setError((e as Error).message)}}
 useEffect(()=>{load()},[]);
 async function action(project:Project,kind:'duplicate'|'delete'){
  if(kind==='delete'&&!confirm(`Delete “${project.name}” and its revisions? This cannot be undone.`))return;
  try{await api(`/projects/${project.id}${kind==='duplicate'?'/duplicate':''}`,{method:kind==='delete'?'DELETE':'POST'});await load()}catch(e){setError((e as Error).message)}
 }
 return <main className="dashboard"><header className="dashboard-header"><Brand/><span className="header-divider"/><span className="muted">Home design</span><div className="header-spacer"/><a className="nilam-header-link" href={NILAM_URL}><ArrowLeft size={16}/> Explore land</a></header><div className="dashboard-content"><div className="dashboard-heading"><div><span className="eyebrow">NILAM · HOME DESIGN</span><h1>Saved designs<span>.</span></h1><p>Return to a floor plan, or begin with another site.</p></div><a className="button primary" href={DESIGN_BASE+'/'}><Plus size={18}/> New design</a></div><div className="projects-toolbar"><h2>Designs <span>{projects.length}</span></h2><label className="search-input"><Search size={17}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search designs" aria-label="Search designs"/></label></div>{error&&<p className="error" role="alert">{error}</p>}<div className="project-grid"><a className="new-project-card" href={DESIGN_BASE+'/'}><span><Plus size={24}/></span><h3>Start a new home.</h3><p>Set plot dimensions and rooms.</p></a>{projects.filter(p=>p.name.toLowerCase().includes(query.toLowerCase())).map(p=><article className="project-card" key={p.id}><a href={`${DESIGN_BASE}/workspace/${p.id}`} className="project-preview">{p.layout?<Plan layout={p.layout} mini/>:<FolderOpen size={50} strokeWidth={1}/>}<span className="project-badge">{p.layout?'CONCEPT DESIGN':'DRAFT'}</span><span className="preview-open"><ArrowUpRight size={18}/></span></a><div className="project-card-info"><a href={`${DESIGN_BASE}/workspace/${p.id}`}><h3>{p.name}</h3></a><p>{p.specification.plot_width} × {p.specification.plot_length} {p.specification.unit==='feet'?'ft':'m'}<span>·</span>{p.specification.floors} floors</p>{p.specification.site_context&&<p className="project-site-label"><MapPin size={13}/>{p.specification.site_context.district} · {p.specification.site_context.lat.toFixed(4)}, {p.specification.site_context.lon.toFixed(4)}</p>}<div className="project-card-bottom"><small>Updated {new Date(p.updated_at).toLocaleDateString()}</small><div><button className="icon-button" aria-label={`Duplicate ${p.name}`} onClick={()=>action(p,'duplicate')}><Copy size={14}/></button><button className="icon-button" aria-label={`Delete ${p.name}`} onClick={()=>action(p,'delete')}><Trash2 size={14}/></button></div></div></div></article>)}</div>{loaded&&projects.length===0&&<p className="empty-hint">Your first design will appear here.</p>}</div></main>
}
