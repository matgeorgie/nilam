'use client';
import {useEffect,useState} from 'react';
import {ArrowLeft,FolderOpen,MapPin} from 'lucide-react';
import NewProject from '@/components/NewProject';
import Brand from '@/components/Brand';
import {DESIGN_BASE,NILAM_URL,siteFromSearch} from '@/lib/nilam';
import type {SiteContext} from '@/lib/types';

export default function Home(){
 const [site,setSite]=useState<SiteContext|null>(null);
 useEffect(()=>setSite(siteFromSearch(window.location.search)),[]);
 return <main className="nilam-design-entry">
  <header className="nilam-design-nav"><div className="nilam-design-nav-brand"><a href={NILAM_URL} className="nilam-wordmark">nilam<span>.</span></a><span className="nilam-nav-divider"/><Brand/><span className="nilam-extension-label">Home design</span></div><div className="nilam-design-nav-links"><a href={NILAM_URL}><ArrowLeft size={16}/> Explore land</a><a href={DESIGN_BASE+'/projects'}><FolderOpen size={16}/> Saved designs</a></div></header>
  <section className="nilam-design-intro"><div className="nilam-intro-copy"><span className="nilam-kicker">FROM LAND TO LIVING</span><h1>Now, imagine a home here.</h1><p>Shape a floor plan for the place you selected. Start with your plot measurements, then choose the rooms and explore the result in 2D or 3D.</p></div>{site&&<div className="nilam-site-summary"><MapPin size={19}/><div><span>Selected in Nilam</span><strong>{site.district}</strong><small>{site.lat.toFixed(5)}, {site.lon.toFixed(5)}{site.suitability_percent!==null?` · ${Math.round(site.suitability_percent)}% screening score`:''}</small></div></div>}</section>
  <NewProject onClose={()=>{location.href=site?NILAM_URL:DESIGN_BASE+'/projects'}} siteContext={site} embedded/>
 </main>;
}
