import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import mapboxgl from "mapbox-gl";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "mapbox-gl/dist/mapbox-gl.css";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";
import "./style.css";

const districts = ["Kasaragod", "Kannur", "Wayanad", "Kozhikode", "Malappuram", "Palakkad", "Thrissur", "Ernakulam", "Idukki", "Kottayam", "Alappuzha", "Pathanamthitta", "Kollam", "Thiruvananthapuram"];
const names = {
  annual_rainfall:"Annual rainfall", aspect:"Slope orientation", clay_content:"Clay content", distance_to_water:"Distance to mapped water", elevation:"Elevation", flood_occurrence:"Persistent surface water", land_cover_class:"Land cover", mean_humidity:"Humidity", mean_temperature:"Temperature", mean_wind_speed:"Wind speed", ndvi:"Vegetation density", organic_carbon:"Soil organic carbon", sand_content:"Sand content", slope:"Ground slope", soil_ph:"Soil pH", terrain_ruggedness_index:"Terrain ruggedness", water_content:"Soil water retention", flood_level_10yr_m:"10-year flood depth", flood_level_25yr_m:"25-year flood depth", flood_level_50yr_m:"50-year flood depth", flood_level_100yr_m:"100-year flood depth", flood_level_200yr_m:"200-year flood depth", flood_level_500yr_m:"500-year flood depth", gsi_landslide_code:"GSI landslide class", dist_nearest_road:"Nearest road", dist_nearest_highway:"Nearest highway", dist_nearest_hospital:"Nearest hospital", dist_nearest_school:"Nearest school", dist_nearest_quarry:"Nearest quarry", dist_nearest_bus_stop:"Nearest bus stop", dist_nearest_railway_station:"Nearest railway station", dist_nearest_pharmacy:"Nearest pharmacy", dist_nearest_shop:"Nearest shop", dist_nearest_bank:"Nearest bank", dist_nearest_park:"Nearest park", dist_nearest_power_line:"Nearest power line", dist_nearest_waste_facility:"Nearest waste facility", dist_nearest_industrial:"Nearest industrial site"
};
const modelNames = {extra_trees:"ExtraTrees", feature_transformer:"Feature Transformer", tabpfn:"TabPFN 3.5"};
const distanceFeatures = new Set(Object.keys(names).filter((x)=>x.startsWith("dist_")).concat(["distance_to_water"]));
const units = {annual_rainfall:"mm/yr",aspect:"°",clay_content:"%",distance_to_water:"m",elevation:"m",flood_occurrence:"%",mean_humidity:"%",mean_temperature:"°C",mean_wind_speed:"m/s",ndvi:"",organic_carbon:"g/kg",sand_content:"%",slope:"°",soil_ph:"pH",terrain_ruggedness_index:"m",water_content:"%",flood_level_10yr_m:"m",flood_level_25yr_m:"m",flood_level_50yr_m:"m",flood_level_100yr_m:"m",flood_level_200yr_m:"m",flood_level_500yr_m:"m"};
const fmt=(v,d=1)=>v==null||Number.isNaN(Number(v))?"Unavailable":Number(v).toLocaleString("en-IN",{maximumFractionDigits:d});
const valueLabel=(item)=>{
  if(item.value==null)return "No reading";
  if(distanceFeatures.has(item.feature))return item.value>=1000?`${fmt(item.value/1000)} km`:`${fmt(item.value,0)} m`;
  if(item.feature==="gsi_landslide_code")return ["Not mapped","Low","Moderate","High"][Math.round(item.value)]||fmt(item.value);
  if(item.feature==="land_cover_class")return ["Water","Trees","Grass","Flooded vegetation","Crops","Scrub","Built area","Bare ground","Snow/ice"][Math.round(item.value)]||fmt(item.value);
  return `${fmt(item.value)}${units[item.feature]?` ${units[item.feature]}`:""}`;
};
async function api(url,options){const r=await fetch(url,options);if(!r.ok){const e=await r.json().catch(()=>({detail:"Request failed"}));throw new Error(e.detail||"Request failed");}return r.json();}
function Icon({type}){const path=type==="area"?"M4 5l7-2 9 5-3 11-10 1zM11 3v17M4 5l13 14":type==="satellite"?"M5 19l14-14M14 4l6 6-4 4-6-6zM4 14l6 6M3 21h8":"M12 3v18M3 12h18M12 7a5 5 0 100 10 5 5 0 000-10z";return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path}/></svg>}

function App(){
  const [config,setConfig]=useState(null),[report,setReport]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState(""),[mapError,setMapError]=useState("");
  const [mode,setMode]=useState("point"),[style,setStyleMode]=useState("normal"),[model,setModel]=useState("tabpfn"),[district,setDistrict]=useState("");
  const container=useRef(),map=useRef(),draw=useRef(),marker=useRef(),boundaries=useRef(),latest=useRef(),requestId=useRef(0),dialog=useRef(),reportPanel=useRef();
  latest.current={mode,model};
  useEffect(()=>{api("/api/config").then(setConfig).catch((e)=>setError(e.message));},[]);
  useEffect(()=>{if(report&&window.innerWidth<=780)requestAnimationFrame(()=>reportPanel.current?.scrollIntoView({behavior:"smooth",block:"start"}));},[report]);
  const run=async(url,body)=>{const id=++requestId.current;setLoading(true);setError("");setReport(null);try{const result=await api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(id===requestId.current)setReport(result);}catch(e){if(id===requestId.current)setError(e.message);}finally{if(id===requestId.current)setLoading(false);}};
  const analyzePoint=(lon,lat)=>{marker.current?.remove();marker.current=new mapboxgl.Marker({color:"#176149"}).setLngLat([lon,lat]).addTo(map.current);run("/api/analyze",{lat,lon,radius_m:150,model:latest.current.model});};
  const analyzeArea=(feature)=>{marker.current?.remove();run("/api/analyze-area",{geometry:feature.geometry,model:latest.current.model});};
  const addBoundaries=()=>{const m=map.current,b=boundaries.current;if(!m||!b||m.getSource("kerala"))return;m.addSource("kerala",{type:"geojson",data:b.state});m.addLayer({id:"kerala-shade",type:"fill",source:"kerala",paint:{"fill-color":"#147a58","fill-opacity":style==="satellite"?.05:.045}});m.addLayer({id:"kerala-line",type:"line",source:"kerala",paint:{"line-color":style==="satellite"?"#d6f5e7":"#215c49","line-width":1.4}});m.addSource("districts",{type:"geojson",data:b.districts});m.addLayer({id:"district-lines",type:"line",source:"districts",paint:{"line-color":style==="satellite"?"#b5d8cb":"#7b9b8f","line-width":.65,"line-dasharray":[3,3]}});};
  useEffect(()=>{
    if(!config||map.current||!container.current)return;if(!config.mapbox_token){setMapError("Mapbox token missing. Add MAPBOX_PUBLIC_TOKEN to .env.");return;}
    mapboxgl.accessToken=config.mapbox_token;const m=new mapboxgl.Map({container:container.current,style:"mapbox://styles/mapbox/streets-v12",center:[76.25,10.5],zoom:6.6,minZoom:5,maxZoom:19,maxBounds:[[73.7,7.5],[79,14]],attributionControl:true});map.current=m;
    m.addControl(new mapboxgl.NavigationControl({showCompass:false}),"bottom-right");
    const d=new MapboxDraw({displayControlsDefault:false,controls:{},defaultMode:"simple_select"});draw.current=d;m.addControl(d,"top-right");
    m.on("click",(e)=>{if(latest.current.mode==="point"&&d.getMode()==="simple_select")analyzePoint(e.lngLat.lng,e.lngLat.lat);});
    m.on("draw.create",(e)=>{const f=e.features[0];d.deleteAll();d.add(f);d.changeMode("simple_select");analyzeArea(f);});
    m.on("draw.update",(e)=>e.features[0]&&analyzeArea(e.features[0]));
    m.on("draw.delete",()=>setReport(null));
    m.on("error",()=>setMapError("Some map tiles could not load."));
    m.on("load",async()=>{try{const [state,ds]=await Promise.all([api("/api/layers/kerala"),api("/api/layers/districts")]);boundaries.current={state,districts:ds};addBoundaries();m.fitBounds([[74.85,8.15],[77.45,12.9]],{padding:25,duration:0});}catch(e){setMapError(e.message);}});
    return()=>{m.remove();map.current=null;};
  },[config]);
  useEffect(()=>{if(!map.current)return;map.current.setStyle(style==="satellite"?"mapbox://styles/mapbox/satellite-streets-v12":"mapbox://styles/mapbox/streets-v12");map.current.once("style.load",addBoundaries);},[style]);
  const chooseMode=(next)=>{setMode(next);setReport(null);marker.current?.remove();draw.current?.deleteAll();if(next==="area")draw.current?.changeMode("draw_polygon");else draw.current?.changeMode("simple_select");};
  const clear=()=>{setReport(null);setError("");marker.current?.remove();draw.current?.deleteAll();if(mode==="area")draw.current?.changeMode("draw_polygon");};
  const changeModel=(next)=>{setModel(next);setReport(null);setError("");marker.current?.remove();draw.current?.deleteAll();if(mode==="area")draw.current?.changeMode("draw_polygon");};
  const flyDistrict=(name)=>{setDistrict(name);const feature=boundaries.current?.districts.features.find((f)=>f.properties.name===name);if(!feature)return;const coords=feature.geometry.type==="Polygon"?feature.geometry.coordinates.flat():feature.geometry.coordinates.flat(2);const bounds=coords.reduce((b,c)=>b.extend(c),new mapboxgl.LngLatBounds(coords[0],coords[0]));map.current.fitBounds(bounds,{padding:45,duration:700});};
  const download=()=>{const blob=new Blob([JSON.stringify(report,null,2)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="nilam-assessment.json";a.click();URL.revokeObjectURL(a.href);};
  const explanation=report?.prediction?.explanation, factors=explanation?[...explanation.contributions].sort((a,b)=>Math.abs(b.contribution)-Math.abs(a.contribution)).slice(0,8):[];
  const positive=factors.filter((x)=>x.contribution>0).slice(0,4),negative=factors.filter((x)=>x.contribution<0).slice(0,4);
  const score=report?.prediction?.suitability_percent;
  return <>
    <header className="masthead"><a className="brand" href="#">nilam<span>Kerala land intelligence</span></a><button className="method-link" onClick={()=>dialog.current?.showModal()}>Research method</button></header>
    <main>
      <section className="intro"><div><h1>Understand land<br/>before you build.</h1><p>Select a point or draw a site boundary anywhere in Kerala. Nilam combines 38 public-data features with a statewide TabPFN model and SHAP explanations.</p></div><span>14 districts · 1,400 training locations · 38 features</span></section>
      <section className="workspace">
        <div className="map-column">
          <div className="map-tools">
            <select aria-label="Go to district" value={district} onChange={(e)=>flyDistrict(e.target.value)}><option value="">All Kerala</option>{districts.map((d)=><option key={d}>{d}</option>)}</select>
            <div className="segmented" aria-label="Selection type"><button aria-pressed={mode==="point"} className={mode==="point"?"active":""} onClick={()=>chooseMode("point")}><Icon type="point"/>Point</button><button aria-pressed={mode==="area"} className={mode==="area"?"active":""} onClick={()=>chooseMode("area")}><Icon type="area"/>Draw area</button></div>
            <div className="segmented" aria-label="Map style"><button aria-pressed={style==="normal"} className={style==="normal"?"active":""} onClick={()=>setStyleMode("normal")}>Map</button><button aria-pressed={style==="satellite"} className={style==="satellite"?"active":""} onClick={()=>setStyleMode("satellite")}><Icon type="satellite"/>Satellite</button></div>
            <button className="clear" onClick={clear}>Clear</button>
          </div>
          <div className="map-frame"><div ref={container} className="map"/>{!report&&!loading&&<div className="map-prompt"><Icon type={mode}/><strong>{mode==="area"?"Click to trace the site boundary":"Click any location in Kerala"}</strong><span>{mode==="area"?"Close the polygon to run the assessment":"Zoom in for parcel-level selection"}</span></div>}{mapError&&<div className="map-error">{mapError}</div>}</div>
          <div className="map-footer"><span>{mode==="area"?"Area mode samples up to 9 locations across the polygon":"Point mode evaluates a 150 m neighbourhood"}</span><span>Normal and satellite basemaps by Mapbox</span></div>
        </div>
        <aside ref={reportPanel} className="report-column" aria-live="polite">
          <div className="report-toolbar"><div><strong>Suitability assessment</strong><span>Experimental public-data model</span></div><label>Model<select value={model} onChange={(e)=>changeModel(e.target.value)}><option value="tabpfn">TabPFN 3.5</option><option value="feature_transformer">Feature Transformer</option><option value="extra_trees">ExtraTrees</option></select></label></div>
          {loading?<div className="loading"><div className="skeleton score-skeleton"/><div className="skeleton"/><div className="skeleton short"/><p>Reading satellite, terrain, soil and access data…</p></div>:error?<div className="empty error"><h2>Assessment failed</h2><p>{error}</p><button onClick={clear}>Try another selection</button></div>:!report?<div className="empty"><h2>Your land report appears here.</h2><p>The result includes a suitability percentage, spatial variation for polygons, and the features that moved the model score.</p><div className="empty-steps"><span><b>1</b>Select a point or area</span><span><b>2</b>Review the score</span><span><b>3</b>Inspect SHAP drivers</span></div></div>:report.prediction.status!=="available"?<div className="empty error"><h2>Analysis unavailable</h2><p>{report.prediction.reason||"The model could not produce a stable result. Choose another model or selection."}</p><button onClick={clear}>Choose another location</button></div>:<>
            <div className="score-panel"><div className="score-number"><strong>{fmt(score,0)}<small>%</small></strong><span>model suitability</span></div><div className="score-copy"><span className={`status status-${Math.floor((score||0)/25)}`}>{report.outcome}</span><h2>{report.district}</h2><p>{report.reason}</p></div><div className="score-track"><i style={{width:`${score}%`}}/></div><div className="score-scale"><span>More constraints</span><span>More favourable</span></div></div>
            {report.location.selection_type==="polygon"&&<div className="spatial"><div><span>Area</span><strong>{fmt(report.location.area_m2,0)} m²</strong></div><div><span>Sampled</span><strong>{report.prediction.spatial_summary.samples} points</strong></div><div><span>Variation</span><strong>{fmt(report.prediction.spatial_summary.minimum_percent,0)}–{fmt(report.prediction.spatial_summary.maximum_percent,0)}%</strong></div></div>}
            <div className="report-body"><div className="summary-head"><div><h3>What shaped this score</h3><p>SHAP attributes the difference from the model’s statewide reference score.</p></div><button onClick={download}>Export JSON</button></div>
              <div className="factor-columns"><FactorList title="Supported suitability" items={positive}/><FactorList title="Reduced suitability" items={negative}/></div>
              <h3 className="section-title">Influence by evidence group</h3><div className="group-list">{explanation.groups.slice(0,7).map((g)=><div key={g.group}><span>{g.group}</span><div><i className={g.contribution>=0?"up":"down"} style={{width:`${Math.min(100,Math.abs(g.contribution)*5)}%`}}/></div><strong>{g.contribution>0?"+":""}{fmt(g.contribution)} pp</strong></div>)}</div>
              <details><summary>How to read this result</summary><p>The score is an ordinal model index: class probabilities are weighted from 8% for “screen out” to 90% for “higher suitability.” It is not the probability that construction is safe.</p><p>{explanation.method}. {explanation.meaning}</p></details>
            </div>
            <div className="model-strip"><span>{modelNames[report.prediction.model]}</span><span>Reference {fmt(explanation.base_value,0)}% → result {fmt(explanation.output_value,0)}%</span></div>
          </>}
        </aside>
      </section>
      <section className="research"><div><h2>Built as a spatial ML study.</h2><p>District-held-out testing measures transfer to unseen parts of Kerala. TabPFN reached {fmt((config?.evaluation?.models?.tabpfn_3_5_fast?.test?.macro_f1||0)*100,1)}% macro-F1 on the experimental weak labels.</p></div><div><strong>38</strong><span>model features</span></div><div><strong>5</strong><span>held-out districts</span></div><div><strong>3</strong><span>model families</span></div></section>
    </main>
    <footer><strong>nilam</strong><span>Research screening for Kerala · not engineering or legal approval</span></footer>
    <dialog ref={dialog} className="methods"><button className="dialog-close" onClick={()=>dialog.current?.close()} aria-label="Close">×</button><h2>Research method</h2><p>Nilam compares ExtraTrees, a trained feature-token Transformer, pretrained TabPFN 3.5, and a fine-tuned TabPFN experiment. Entire districts are held out during validation and testing.</p><div className="method-grid"><div><strong>1,400</strong><span>statewide samples</span></div><div><strong>0.845</strong><span>test macro-F1</span></div><div><strong>SHAP</strong><span>local attribution</span></div></div><h3>Scientific limit</h3><p>The target is generated from transparent public-data rules because verified construction outcomes and expert labels are not yet available. Scores evaluate agreement with that target. They do not certify bearing capacity, legal compliance or buildability.</p></dialog>
  </>;
}
function FactorList({title,items}){return <section className="factor-list"><h4>{title}</h4>{items.length?items.map((item)=><div className="factor" key={item.feature}><div><strong>{names[item.feature]||item.feature}</strong><span>{item.group} · {valueLabel(item)}</span></div><b className={item.contribution>=0?"up-text":"down-text"}>{item.contribution>0?"+":""}{fmt(item.contribution)} pp</b></div>):<p>No major driver in this direction.</p>}</section>}
createRoot(document.getElementById("root")).render(<App/>);
