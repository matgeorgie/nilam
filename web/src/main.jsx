import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "";
const KERALA_CENTER = { lat: 10.36, lng: 76.27 };
const DISTRICTS = ["Kasaragod", "Kannur", "Wayanad", "Kozhikode", "Malappuram", "Palakkad", "Thrissur", "Ernakulam", "Idukki", "Kottayam", "Alappuzha", "Pathanamthitta", "Kollam", "Thiruvananthapuram"];
const FEATURE_NAMES = {
  annual_rainfall: "Annual rainfall", aspect: "Slope orientation", clay_content: "Clay content",
  distance_to_water: "Distance to mapped water", elevation: "Elevation", flood_occurrence: "Persistent surface water",
  land_cover_class: "Land cover", mean_humidity: "Humidity", mean_temperature: "Temperature",
  mean_wind_speed: "Wind speed", ndvi: "Vegetation density", organic_carbon: "Soil organic carbon",
  sand_content: "Sand content", slope: "Ground slope", soil_ph: "Soil pH",
  terrain_ruggedness_index: "Terrain ruggedness", water_content: "Soil water retention",
  flood_level_10yr_m: "10-year flood depth", flood_level_25yr_m: "25-year flood depth",
  flood_level_50yr_m: "50-year flood depth", flood_level_100yr_m: "100-year flood depth",
  flood_level_200yr_m: "200-year flood depth", flood_level_500yr_m: "500-year flood depth",
  gsi_landslide_code: "GSI landslide class", dist_nearest_road: "Nearest road",
  dist_nearest_highway: "Nearest highway", dist_nearest_hospital: "Nearest hospital",
  dist_nearest_school: "Nearest school", dist_nearest_quarry: "Nearest quarry",
  dist_nearest_bus_stop: "Nearest bus stop", dist_nearest_railway_station: "Nearest railway station",
  dist_nearest_pharmacy: "Nearest pharmacy", dist_nearest_shop: "Nearest shop",
  dist_nearest_bank: "Nearest bank", dist_nearest_park: "Nearest park",
  dist_nearest_power_line: "Nearest power line", dist_nearest_waste_facility: "Nearest waste facility",
  dist_nearest_industrial: "Nearest industrial site",
};
const DISTANCES = new Set(Object.keys(FEATURE_NAMES).filter((name) => name.startsWith("dist_")).concat(["distance_to_water"]));
const UNITS = { annual_rainfall: "mm/yr", aspect: "°", clay_content: "%", elevation: "m", flood_occurrence: "%", mean_humidity: "%", mean_temperature: "°C", mean_wind_speed: "m/s", organic_carbon: "g/kg", sand_content: "%", slope: "°", soil_ph: "pH", terrain_ruggedness_index: "m", water_content: "%", flood_level_10yr_m: "m", flood_level_25yr_m: "m", flood_level_50yr_m: "m", flood_level_100yr_m: "m", flood_level_200yr_m: "m", flood_level_500yr_m: "m" };

const fmt = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? "Unavailable" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: digits });
const api = async (path, options = {}) => {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return response.json();
};
const post = (path, body, signal) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
const valueLabel = (item) => {
  if (item.value == null) return "No reading";
  if (DISTANCES.has(item.feature)) return item.value >= 1000 ? `${fmt(item.value / 1000)} km` : `${fmt(item.value, 0)} m`;
  if (item.feature === "gsi_landslide_code") return ["Not mapped", "Low", "Moderate", "High"][Math.round(item.value)] || fmt(item.value);
  if (item.feature === "land_cover_class") return ["Water", "Trees", "Grass", "Flooded vegetation", "Crops", "Scrub", "Built area", "Bare ground", "Snow / ice"][Math.round(item.value)] || fmt(item.value);
  return `${fmt(item.value)}${UNITS[item.feature] ? ` ${UNITS[item.feature]}` : ""}`;
};

function Icon({ type }) {
  const paths = {
    point: "M12 3v18M3 12h18M12 7a5 5 0 100 10 5 5 0 000-10z",
    area: "M4 5l7-2 9 5-3 11-10 1zM11 3v17M4 5l13 14",
    satellite: "M5 19l14-14M14 4l6 6-4 4-6-6zM4 14l6 6M3 21h8",
    table: "M4 5h16v14H4zM4 10h16M9 5v14",
    merge: "M5 5v3c0 3 2 4 7 4s7 1 7 4v3M19 5v3M12 12v7",
    search: "M11 4a7 7 0 100 14 7 7 0 000-14zm5 12l5 5",
    mic: "M12 3a3 3 0 00-3 3v5a3 3 0 006 0V6a3 3 0 00-3-3zM5 11a7 7 0 0014 0M12 18v3",
    bookmark: "M6 4h12v17l-6-4-6 4z",
    street: "M4 20V7l8-4 8 4v13M8 20v-8h8v8M9 8h6",
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={paths[type] || paths.point} /></svg>;
}

let mapsPromise;
function loadGoogleMaps(key) {
  if (window.google?.maps?.importLibrary) return Promise.resolve(window.google.maps);
  if (mapsPromise) return mapsPromise;
  mapsPromise = new Promise((resolve, reject) => {
    window.__nilamMapsReady = () => resolve(window.google.maps);
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=places,marker&v=weekly&callback=__nilamMapsReady&loading=async`;
    script.async = true;
    script.onerror = () => reject(new Error("Google Maps could not load. Check the browser key and enabled APIs."));
    document.head.appendChild(script);
  });
  return mapsPromise;
}

function Stage({ stage }) {
  const items = [
    ["mapped", "Mapped evidence", "TabPFN reads 38 land features"],
    ["satellite", "Seasonal satellite", "TerraMind reads dry + monsoon imagery"],
    ["explained", "Explanation", "SHAP attributes the final estimate"],
  ];
  const index = { mapped: 0, satellite: 1, explained: 2 }[stage] ?? -1;
  return <div className="stage" aria-label="Analysis progress">{items.map((item, i) => <div className={i <= index ? "done" : i === index + 1 ? "active" : ""} key={item[0]}><i>{i < index ? "✓" : i + 1}</i><span><strong>{item[1]}</strong><small>{item[2]}</small></span></div>)}</div>;
}

function FusionTrace({ data }) {
  if (!data) return null;
  const weights = data.routing_weights || {};
  const scores = data.branch_scores || {};
  const streams = [
    { icon: "satellite", title: "TerraMind", detail: "Two seasonal Sentinel-2 composites", weight: weights.terramind || 0, score: scores.terramind },
    { icon: "table", title: "TabPFN 3.5", detail: "38 mapped terrain, hazard and access features", weight: weights.tabpfn || 0, score: scores.tabpfn },
  ];
  return <section className="fusion-trace">
    <div className="fusion-heading"><div><strong>Two experts, one calibrated result</strong><span>{data.architecture}</span></div><b><i />Quality-gated fusion</b></div>
    {streams.map((stream) => <div className="fusion-stream" key={stream.title}>
      <Icon type={stream.icon} />
      <div className="fusion-stream-copy"><strong>{stream.title}</strong><span>{stream.detail}</span><div className="route-track"><i style={{ width: `${stream.weight}%` }} /></div></div>
      <div className="fusion-numbers"><strong>{stream.score == null ? "Pending" : `${fmt(stream.score, 0)}%`}</strong><span>{fmt(stream.weight, 0)}% influence</span></div>
    </div>)}
    <div className="fusion-result"><Icon type="merge" /><span>Calibrated estimate</span><strong>{scores.fused == null ? "Pending" : `${fmt(scores.fused, 0)}%`}</strong></div>
    <p>Influence is validation-calibrated model weighting. It is different from SHAP feature importance.</p>
  </section>;
}

function FactorList({ title, items, kind }) {
  return <section className="factor-list"><h4>{title}</h4>{items.length ? items.map((item) => <div className="factor" key={item.feature}>
    <div><strong>{FEATURE_NAMES[item.feature] || item.feature}</strong><span>{valueLabel(item)}</span></div>
    <b className={kind}>{item.contribution > 0 ? "+" : ""}{fmt(item.contribution)} pp</b>
  </div>) : <p>No strong factors in this direction.</p>}</section>;
}

function Requirements({ query, setQuery, requirements, setRequirements, interpreting, onInterpret, recording, onRecord }) {
  const update = (key, value) => setRequirements((current) => ({ ...current, [key]: value }));
  return <div className="requirements">
    <div className="request-compose">
      <label htmlFor="land-request">Describe the home and surroundings you want</label>
      <textarea id="land-request" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Example: A quiet, green place in Thrissur, within 5 km of a hospital and away from flood-prone land." />
      <div><button className="secondary" onClick={onRecord}><Icon type="mic" />{recording ? "Stop recording" : "Speak in English"}</button><button className="secondary" disabled={!query.trim() || interpreting} onClick={onInterpret}>{interpreting ? "Interpreting…" : "Interpret request"}</button></div>
    </div>
    <div className="semantic-note"><strong>Local semantic planner</strong><span>Laya turns your request into reviewable filters. Exact distances stay visible and editable.</span></div>
    <div className="requirement-grid">
      <label>Hospital within <span><input type="number" min="0.5" step="0.5" value={requirements.max_hospital_km ?? ""} onChange={(e) => update("max_hospital_km", e.target.value ? Number(e.target.value) : undefined)} /> km</span></label>
      <label>School within <span><input type="number" min="0.5" step="0.5" value={requirements.max_school_km ?? ""} onChange={(e) => update("max_school_km", e.target.value ? Number(e.target.value) : undefined)} /> km</span></label>
      <label>Road within <span><input type="number" min="0.1" step="0.1" value={requirements.max_road_km ?? ""} onChange={(e) => update("max_road_km", e.target.value ? Number(e.target.value) : undefined)} /> km</span></label>
      <label>Maximum slope <span><input type="number" min="1" max="45" value={requirements.max_slope ?? 30} onChange={(e) => update("max_slope", Number(e.target.value))} /> °</span></label>
    </div>
    <div className="checks">
      {[['prefer_quiet', 'Quiet surroundings'], ['prefer_green', 'Greener setting'], ['prefer_transit', 'Public transport'], ['prefer_open_land', 'Apparently open land']].map(([key, label]) => <label key={key}><input type="checkbox" checked={Boolean(requirements[key])} onChange={(e) => update(key, e.target.checked)} />{label}</label>)}
    </div>
    <div className="safeguards"><span>Always applied</span><strong>Exclude mapped water · high flood depth · high landslide class</strong></div>
  </div>;
}

function App() {
  const [config, setConfig] = useState(null);
  const [workspace, setWorkspace] = useState("assess");
  const [mode, setMode] = useState("point");
  const [mapStyle, setMapStyle] = useState("roadmap");
  const [district, setDistrict] = useState("");
  const [report, setReport] = useState(null);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [mapError, setMapError] = useState("");
  const [polygonPoints, setPolygonPoints] = useState(0);
  const [searchDrawing, setSearchDrawing] = useState(false);
  const [searchGeometry, setSearchGeometry] = useState(null);
  const [query, setQuery] = useState("");
  const [requirements, setRequirements] = useState({ avoid_high_flood: true, avoid_high_landslide: true, prefer_open_land: true, max_slope: 30 });
  const [interpreting, setInterpreting] = useState(false);
  const [recording, setRecording] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState(null);
  const [saved, setSaved] = useState(() => JSON.parse(localStorage.getItem("nilam-shortlist") || "[]"));
  const mapElement = useRef(null), searchElement = useRef(null), reportElement = useRef(null);
  const map = useRef(null), maps = useRef(null), boundaries = useRef(null), pointMarker = useRef(null), areaPolygon = useRef(null), candidateMarkers = useRef([]), polygonPath = useRef([]);
  const latest = useRef({}), request = useRef(null), media = useRef(null), mediaChunks = useRef([]), streetDialog = useRef(null), methodsDialog = useRef(null), streetElement = useRef(null);
  latest.current = { workspace, mode, searchDrawing };

  useEffect(() => { api("/api/config").then(setConfig).catch((e) => setError(e.message)); }, []);
  useEffect(() => { localStorage.setItem("nilam-shortlist", JSON.stringify(saved)); }, [saved]);
  useEffect(() => { if (report && window.innerWidth < 900) reportElement.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [report?.prediction?.analysis_stage]);

  const clearOverlays = (includeCandidates = false) => {
    pointMarker.current?.setMap?.(null); pointMarker.current = null;
    areaPolygon.current?.setMap(null); areaPolygon.current = null;
    polygonPath.current = []; setPolygonPoints(0);
    if (includeCandidates) { candidateMarkers.current.forEach((marker) => marker.setMap?.(null)); candidateMarkers.current = []; }
  };

  const runProgressive = async (path, body) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setReport(null); setError(""); setStage("mapped");
    try {
      const preview = await post(path, { ...body, detail: "preview" }, controller.signal);
      setReport(preview); setStage("satellite");
      if (path !== "/api/analyze-area") {
        const full = await post(path, { ...body, detail: "full" }, controller.signal);
        setReport(full); setStage("explained");
      }
      const explained = await post(path, { ...body, detail: "explain" }, controller.signal);
      setReport(explained); setStage("complete");
    } catch (e) {
      if (e.name !== "AbortError") { setError(e.message); setStage(""); }
    }
  };

  const markPoint = (lat, lng) => {
    pointMarker.current?.setMap?.(null);
    if (window.google?.maps && map.current) {
      pointMarker.current = new window.google.maps.Marker({ map: map.current, position: { lat, lng }, title: "Selected site" });
    }
  };
  const analyzePoint = (lat, lng) => { clearOverlays(false); markPoint(lat, lng); runProgressive("/api/analyze", { lat, lon: lng, radius_m: 150 }); };

  const finishPolygon = () => {
    if (polygonPath.current.length < 3) return;
    const path = [...polygonPath.current];
    areaPolygon.current?.setMap(null);
    areaPolygon.current = new window.google.maps.Polygon({ map: map.current, paths: path, strokeColor: "#176149", strokeWeight: 2, fillColor: "#176149", fillOpacity: .16, editable: true });
    const geometry = { type: "Polygon", coordinates: [[...path.map((p) => [p.lng, p.lat]), [path[0].lng, path[0].lat]]] };
    polygonPath.current = []; setPolygonPoints(0);
    runProgressive("/api/analyze-area", { geometry });
  };

  useEffect(() => {
    if (!config || map.current || !mapElement.current) return;
    if (!config.google_maps_api_key) { setMapError("Add GOOGLE_MAPS_API_KEY to .env to load search, map and Street View."); return; }
    let alive = true;
    loadGoogleMaps(config.google_maps_api_key).then(async (library) => {
      if (!alive) return;
      maps.current = library;
      map.current = new window.google.maps.Map(mapElement.current, { center: KERALA_CENTER, zoom: 7, minZoom: 6, maxZoom: 20, mapTypeId: "roadmap", mapId: "DEMO_MAP_ID", streetViewControl: false, fullscreenControl: false, mapTypeControl: false, clickableIcons: false, restriction: { latLngBounds: { north: 13.2, south: 7.8, west: 74.6, east: 78.2 }, strictBounds: false } });
      map.current.addListener("click", (event) => {
        const lat = event.latLng.lat(), lng = event.latLng.lng();
        if (latest.current.workspace === "find") {
          if (latest.current.searchDrawing) {
            polygonPath.current = [...polygonPath.current, { lat, lng }]; setPolygonPoints(polygonPath.current.length);
            areaPolygon.current?.setMap(null);
            areaPolygon.current = new window.google.maps.Polygon({ map: map.current, paths: polygonPath.current, strokeColor: "#176149", strokeWeight: 2, fillColor: "#176149", fillOpacity: .13 });
          }
          return;
        }
        if (latest.current.mode === "point") analyzePoint(lat, lng);
        else {
          polygonPath.current = [...polygonPath.current, { lat, lng }]; setPolygonPoints(polygonPath.current.length);
          areaPolygon.current?.setMap(null);
          areaPolygon.current = new window.google.maps.Polygon({ map: map.current, paths: polygonPath.current, strokeColor: "#176149", strokeWeight: 2, fillColor: "#176149", fillOpacity: .13 });
        }
      });
      try {
        const [state, districtData] = await Promise.all([api("/api/layers/kerala"), api("/api/layers/districts")]);
        boundaries.current = districtData;
        map.current.data.addGeoJson(state); map.current.data.addGeoJson(districtData);
        map.current.data.setStyle((feature) => ({ fillColor: feature.getProperty("name") ? "transparent" : "#176149", fillOpacity: .035, strokeColor: feature.getProperty("name") ? "#78978b" : "#176149", strokeOpacity: .85, strokeWeight: feature.getProperty("name") ? .7 : 1.5 }));
      } catch (e) { setMapError(e.message); }
      try {
        const { PlaceAutocompleteElement } = await window.google.maps.importLibrary("places");
        const autocomplete = new PlaceAutocompleteElement({ placeholder: "Search a place in Kerala" });
        autocomplete.setAttribute("aria-label", "Search a place in Kerala");
        searchElement.current.replaceChildren(autocomplete);
        autocomplete.addEventListener("gmp-select", async (event) => {
          const place = event.placePrediction.toPlace();
          await place.fetchFields({ fields: ["displayName", "location", "viewport"] });
          if (!place.location) return;
          if (place.viewport) map.current.fitBounds(place.viewport); else { map.current.panTo(place.location); map.current.setZoom(16); }
          if (latest.current.workspace === "assess") analyzePoint(place.location.lat(), place.location.lng());
        });
      } catch { setMapError("Map loaded, but place search is unavailable. Enable Places API (New) for this browser key."); }
    }).catch((e) => setMapError(e.message));
    return () => { alive = false; request.current?.abort(); };
  }, [config]);

  useEffect(() => { map.current?.setMapTypeId(mapStyle); }, [mapStyle]);

  const flyDistrict = (name) => {
    setDistrict(name);
    if (name) { setSearchGeometry(null); setSearchDrawing(false); }
    if (!name || !boundaries.current) { map.current?.setCenter(KERALA_CENTER); map.current?.setZoom(7); return; }
    const feature = boundaries.current.features.find((item) => item.properties.name === name);
    if (!feature) return;
    const bounds = new window.google.maps.LatLngBounds();
    const walk = (node) => typeof node[0] === "number" ? bounds.extend({ lng: node[0], lat: node[1] }) : node.forEach(walk);
    walk(feature.geometry.coordinates); map.current.fitBounds(bounds, 45);
  };

  const startSearchArea = () => {
    clearOverlays(true); setSearchResult(null); setSearchGeometry(null); setDistrict("");
    setSearchDrawing(true); setError("");
  };

  const finishSearchArea = () => {
    if (polygonPath.current.length < 3) return;
    const path = [...polygonPath.current];
    areaPolygon.current?.setMap(null);
    areaPolygon.current = new window.google.maps.Polygon({ map: map.current, paths: path, strokeColor: "#176149", strokeWeight: 2, fillColor: "#176149", fillOpacity: .16 });
    setSearchGeometry({ type: "Polygon", coordinates: [[...path.map((point) => [point.lng, point.lat]), [path[0].lng, path[0].lat]]] });
    polygonPath.current = []; setPolygonPoints(0); setSearchDrawing(false);
  };

  const interpret = async () => {
    setInterpreting(true); setError("");
    try { const result = await post("/api/preferences/interpret", { text: query }); setRequirements((current) => ({ ...current, ...result.requirements })); }
    catch (e) { setError(e.message); }
    finally { setInterpreting(false); }
  };

  const record = async () => {
    if (recording) { media.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaChunks.current = []; media.current = new MediaRecorder(stream);
      media.current.ondataavailable = (event) => mediaChunks.current.push(event.data);
      media.current.onstop = async () => {
        setRecording(false); stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(mediaChunks.current, { type: media.current.mimeType || "audio/webm" });
        try { const result = await api("/api/transcribe", { method: "POST", headers: { "Content-Type": blob.type }, body: blob }); setQuery(result.text); }
        catch (e) { setError(e.message); }
      };
      media.current.start(); setRecording(true);
    } catch (e) { setError(`Microphone unavailable: ${e.message}`); }
  };

  const search = async () => {
    setSearching(true); setError(""); clearOverlays(true);
    try {
      const center = map.current?.getCenter();
      const area = searchGeometry ? { geometry: searchGeometry } : district ? { district } : { center_lat: center?.lat() || KERALA_CENTER.lat, center_lon: center?.lng() || KERALA_CENTER.lng, radius_km: 25 };
      const result = await post("/api/search", { area, query, requirements, limit: 10 }); setSearchResult(result);
      if (window.google?.maps && map.current) {
        const bounds = new window.google.maps.LatLngBounds();
        candidateMarkers.current = result.candidates.map((candidate) => {
          const position = { lat: candidate.lat, lng: candidate.lon }; bounds.extend(position);
          const marker = new window.google.maps.Marker({ map: map.current, position, label: String(candidate.rank), title: `#${candidate.rank} · ${candidate.overall_fit_percent}% fit` });
          marker.addListener("click", () => selectCandidate(candidate)); return marker;
        });
        if (result.candidates.length) map.current.fitBounds(bounds, 70);
      }
    } catch (e) { setError(e.message); }
    finally { setSearching(false); }
  };

  const selectCandidate = (candidate) => {
    setWorkspace("assess"); setMode("point");
    map.current?.panTo({ lat: candidate.lat, lng: candidate.lon }); map.current?.setZoom(17);
    analyzePoint(candidate.lat, candidate.lon);
  };
  const saveCandidate = (candidate) => setSaved((current) => current.some((item) => item.point_id === candidate.point_id) ? current.filter((item) => item.point_id !== candidate.point_id) : [...current, candidate]);

  const showStreetView = async () => {
    if (!report || !window.google) return;
    streetDialog.current?.showModal();
    const location = { lat: report.location.lat, lng: report.location.lon };
    const service = new window.google.maps.StreetViewService();
    try {
      const result = await service.getPanorama({ location, radius: 100 });
      new window.google.maps.StreetViewPanorama(streetElement.current, { position: result.data.location.latLng, pov: { heading: 0, pitch: 0 }, zoom: 1, addressControl: true });
    } catch { streetElement.current.innerHTML = '<div class="street-empty"><strong>No nearby Street View imagery</strong><span>Satellite and mapped evidence remain available.</span></div>'; }
  };

  const download = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "nilam-assessment.json"; link.click(); URL.revokeObjectURL(link.href);
  };

  const explanation = report?.prediction?.explanation;
  const factors = useMemo(() => explanation?.contributions ? [...explanation.contributions].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 10) : [], [explanation]);
  const caution = factors.filter((item) => item.feature === "gsi_landslide_code" && Number(item.value) === 0);
  const positive = factors.filter((item) => item.contribution > 0 && !caution.includes(item)).slice(0, 5), negative = factors.filter((item) => item.contribution < 0 && !caution.includes(item)).slice(0, 5);
  const score = report?.prediction?.suitability_percent;
  const loading = Boolean(stage && stage !== "complete");

  return <>
    <header className="masthead"><a className="brand" href="#">nilam<span>Kerala land intelligence</span></a><div className="header-actions"><span className="model-lock"><i />TerraMind + TabPFN</span><button className="method-link" onClick={() => methodsDialog.current?.showModal()}>Research method</button></div></header>
    <main>
      <section className="intro"><div><p className="eyebrow">Public-data decision support for Kerala</p><h1>Understand land<br />before you build.</h1><p>Select a site for a transparent assessment, or describe the home you want and let Nilam rank promising candidate zones.</p></div><span>14 districts · 2 satellite seasons · 38 mapped features</span></section>
      <nav className="workspace-switch" aria-label="Choose workflow"><button className={workspace === "assess" ? "active" : ""} onClick={() => setWorkspace("assess")}><Icon type="point" /><span><strong>Assess a site</strong><small>Click, search or draw a known location</small></span></button><button className={workspace === "find" ? "active" : ""} onClick={() => setWorkspace("find")}><Icon type="search" /><span><strong>Find matching land</strong><small>Rank candidate zones for your needs</small></span></button></nav>
      <section className="workspace">
        <div className="map-column">
          <div className="map-tools">
            <div ref={searchElement} className="place-search"><span>Loading place search…</span></div>
            <select aria-label="Go to district" value={district} onChange={(e) => flyDistrict(e.target.value)}><option value="">All Kerala / map centre</option>{DISTRICTS.map((name) => <option key={name}>{name}</option>)}</select>
            {workspace === "assess" ? <div className="segmented" aria-label="Selection type"><button className={mode === "point" ? "active" : ""} onClick={() => { clearOverlays(false); setMode("point"); }}><Icon type="point" />Point</button><button className={mode === "area" ? "active" : ""} onClick={() => { clearOverlays(false); setMode("area"); }}><Icon type="area" />Area</button></div> : <button className={`draw-search ${searchDrawing ? "active" : ""}`} onClick={startSearchArea}><Icon type="area" />Draw search area</button>}
            <div className="segmented" aria-label="Map style"><button className={mapStyle === "roadmap" ? "active" : ""} onClick={() => setMapStyle("roadmap")}>Map</button><button className={mapStyle === "hybrid" ? "active" : ""} onClick={() => setMapStyle("hybrid")}><Icon type="satellite" />Satellite</button></div>
          </div>
          <div className="map-frame"><div ref={mapElement} className="map" />
            {!report && !searchResult && !mapError && <div className="map-prompt"><Icon type={workspace === "find" ? searchDrawing ? "area" : "search" : mode} /><strong>{workspace === "find" ? searchDrawing ? "Click corners around the search area" : "Choose a district, draw an area or move the map" : mode === "area" ? "Click corners around the site" : "Click or search for a Kerala location"}</strong><span>{workspace === "find" ? searchDrawing ? "Finish after adding at least three points" : "Nilam searches the chosen boundary or 25 km around the map centre" : mode === "area" ? "Three or more points are required" : "A fast mapped preview appears before satellite verification"}</span></div>}
            {polygonPoints >= 3 && <button className="finish-area" onClick={workspace === "find" ? finishSearchArea : finishPolygon}>Finish {workspace === "find" ? "search area" : "site area"} · {polygonPoints} points</button>}
            {mapError && <div className="map-error">{mapError}</div>}
          </div>
          <div className="map-footer"><span>{workspace === "find" ? "Candidate zones are ranked from the local statewide index" : mode === "area" ? "Area mode samples up to 9 locations" : "Point mode evaluates a 150 m neighbourhood"}</span><span>Google Maps · Street View context where available</span></div>
        </div>

        <aside ref={reportElement} className="report-column" aria-live="polite">
          <div className="report-toolbar"><div><strong>{workspace === "find" ? "Land matcher" : "Suitability assessment"}</strong><span>{workspace === "find" ? "Safety filters + personal preference fit" : "Satellite + mapped evidence fusion"}</span></div><span className="fixed-model">One calibrated model</span></div>
          {workspace === "find" ? <>
            <Requirements query={query} setQuery={setQuery} requirements={requirements} setRequirements={setRequirements} interpreting={interpreting} onInterpret={interpret} recording={recording} onRecord={record} />
            <div className="search-scope"><span>Search area</span><strong>{searchGeometry ? "Custom drawn boundary" : district || "25 km around the map centre"}</strong></div>
            <button className="primary" disabled={searching} onClick={search}><Icon type="search" />{searching ? "Screening candidate zones…" : "Find best-fit zones"}</button>
            {error && <div className="inline-error">{error}</div>}
            {searchResult && <div className="candidate-results"><div className="result-head"><div><strong>{searchResult.candidates.length} candidate zones</strong><span>screened from {fmt(searchResult.searched_points, 0)} indexed points</span></div><small>Suitability and personal fit stay separate</small></div>
              {searchResult.candidates.length ? searchResult.candidates.map((candidate) => <article className="candidate" key={candidate.point_id}>
                <div className="candidate-main"><span className="rank">{candidate.rank}</span><div><strong>{candidate.district}</strong><span>{candidate.advantages.join(" · ") || "Public-data candidate"}</span></div><button aria-label="Save candidate" className={saved.some((item) => item.point_id === candidate.point_id) ? "saved" : ""} onClick={() => saveCandidate(candidate)}><Icon type="bookmark" /></button></div>
                <div className="candidate-score"><div><strong>{fmt(candidate.suitability_percent, 0)}%</strong><span>model suitability</span></div><div><strong>{fmt(candidate.preference_fit_percent, 0)}%</strong><span>preference fit</span></div><div><strong>{fmt(candidate.overall_fit_percent, 0)}%</strong><span>combined rank</span></div></div>
                {candidate.constraints.length > 0 && <p>Review: {candidate.constraints.join(" · ")}</p>}
                <button className="candidate-open" onClick={() => selectCandidate(candidate)}>Verify with TerraMind satellite evidence →</button>
              </article>) : <div className="empty compact"><h2>No indexed zones matched</h2><p>{searchResult.message}</p></div>}
              <p className="candidate-limit">{searchResult.limitation}</p>
            </div>}
          </> : <>
            {searchResult && <button className="back-link" onClick={() => setWorkspace("find")}>← Back to candidate list</button>}
            {loading && <Stage stage={stage} />}
            {error ? <div className="empty error"><h2>Assessment stopped</h2><p>{error}</p><button onClick={() => { setError(""); setStage(""); }}>Choose another location</button></div> : !report ? <div className="empty"><h2>Your land report appears here.</h2><p>Nilam first returns mapped evidence, then adds seasonal TerraMind satellite analysis and SHAP explanation.</p><div className="empty-steps"><span><b>1</b>Select a point or area</span><span><b>2</b>See the score immediately</span><span><b>3</b>Inspect model evidence</span></div></div> : report.prediction.status !== "available" ? <div className="empty error"><h2>Analysis unavailable</h2><p>{report.prediction.reason}</p></div> : <>
              <div className="score-panel"><div className="score-number"><strong>{fmt(score, 0)}<small>%</small></strong><span>model suitability</span></div><div className="score-copy"><span className={`status status-${Math.floor((score || 0) / 25)}`}>{report.outcome}</span><h2>{report.district}</h2><p>{report.reason}</p></div><div className="score-track"><i style={{ width: `${score}%` }} /></div><div className="score-scale"><span>More constraints</span><span>More favourable</span></div></div>
              <div className="score-actions"><button onClick={showStreetView}><Icon type="street" />Street View</button><button onClick={download}>Export evidence</button></div>
              {report.location.selection_type === "polygon" && <div className="spatial"><div><span>Area</span><strong>{fmt(report.location.area_m2, 0)} m²</strong></div><div><span>Sampled</span><strong>{report.prediction.spatial_summary.samples} points</strong></div><div><span>Range</span><strong>{fmt(report.prediction.spatial_summary.minimum_percent, 0)}–{fmt(report.prediction.spatial_summary.maximum_percent, 0)}%</strong></div></div>}
              <FusionTrace data={report.prediction.multimodal} />
              <div className="report-body"><div className="summary-head"><div><h3>Why the score changed</h3><p>{explanation?.status === "ready" ? "SHAP shows mapped features that moved the combined estimate from its reference." : "The conditional SHAP explanation is still being calculated."}</p></div></div>
                {explanation?.status === "ready" ? <><div className="factor-columns"><FactorList title="Raised suitability" items={positive} kind="up" /><FactorList title="Reduced suitability" items={negative} kind="down" /></div>{caution.length > 0 && <div className="caution-factors"><FactorList title="Evidence gaps affecting the model" items={caution} kind="caution" /><p>“Not mapped” is not evidence of low landslide risk. This learned association stays visible for audit, but must be verified independently.</p></div>}<h3 className="section-title">Influence by evidence group</h3><div className="group-list">{explanation.groups.slice(0, 7).map((group) => <div key={group.group}><span>{group.group}{group.group === "Natural hazards" && caution.length ? " *" : ""}</span><div><i className={group.contribution >= 0 ? "up" : "down"} style={{ width: `${Math.min(100, Math.abs(group.contribution) * 5)}%` }} /></div><strong>{group.contribution > 0 ? "+" : ""}{fmt(group.contribution)} pp</strong></div>)}</div>{caution.length > 0 && <p className="group-caveat">* Includes an unmapped-data association; do not interpret it as hazard clearance.</p>}</> : <div className="explanation-pending"><span /><div><strong>Model explanation in progress</strong><p>The score is usable now. SHAP follows without re-running TerraMind.</p></div></div>}
                <details><summary>How to read the percentage</summary><p>The value is an ordinal suitability index made from four model-class probabilities. It is not the probability that a building is safe or legally approvable.</p><p>{report.prediction.limitation}</p></details>
                <div className="unknowns"><h3>Needs on-site verification</h3><p>{(report.unknowns || ["Soil bearing capacity", "Legal and planning compliance", "Drainage and access"]).slice(0, 4).join(" · ")}</p></div>
              </div>
            </>}
          </>}
        </aside>
      </section>
      <section className="research"><div><h2>One model, measured honestly.</h2><p>TabPFN leads the score because it performed better on unseen districts. TerraMind contributes seasonal satellite evidence through a validation-calibrated 8% gate.</p></div><div><strong>0.847</strong><span>fusion test macro-F1</span></div><div><strong>38</strong><span>mapped features</span></div><div><strong>5</strong><span>held-out districts</span></div></section>
    </main>
    <footer><strong>nilam</strong><span>Research screening for Kerala · not engineering, legal or purchase approval</span></footer>

    <dialog ref={methodsDialog} className="methods"><button className="dialog-close" onClick={() => methodsDialog.current?.close()} aria-label="Close">×</button><p className="eyebrow">Research method</p><h2>TerraMind + TabPFN adaptive fusion</h2><p>TabPFN evaluates 38 public-data features. TerraMind encodes dry- and monsoon-season 12-band Sentinel-2 chips. Their four-class probabilities are combined by a validation-calibrated agreement gate.</p><div className="method-grid"><div><strong>1,400</strong><span>statewide study points</span></div><div><strong>0.847</strong><span>fusion test macro-F1</span></div><div><strong>0.850</strong><span>TabPFN test macro-F1</span></div></div><h3>Why TerraMind has 8% influence</h3><p>The vision branch adds independent land-cover context, but it did not beat TabPFN on held-out test districts. The quality gate therefore keeps TabPFN dominant. The difference is small and the targets are weak labels, so neither number is a safety validation.</p><h3>Semantic and voice tools</h3><p>Laya interprets local preference requests. Distil-Whisper transcribes English speech locally. GLiNER2.5-Decide can be enabled as an experimental semantic comparator.</p><h3>Scientific limit</h3><p>The target was generated from transparent public-data rules because verified construction outcomes and expert labels are not yet available. A geotechnical investigation and planning review remain essential.</p></dialog>
    <dialog ref={streetDialog} className="street-dialog"><button className="dialog-close" onClick={() => streetDialog.current?.close()} aria-label="Close">×</button><div><p className="eyebrow">Ground context</p><h2>Nearby Street View</h2><p>Visual context only. Imagery date and road position may differ from the selected land.</p></div><div ref={streetElement} className="street-view" /></dialog>
  </>;
}

createRoot(document.getElementById("root")).render(<App />);
