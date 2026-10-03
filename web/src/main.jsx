import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const KERALA_CENTER = { lat: 10.36, lng: 76.27 };
const DISTRICTS = ["Kasaragod", "Kannur", "Wayanad", "Kozhikode", "Malappuram", "Palakkad", "Thrissur", "Ernakulam", "Idukki", "Kottayam", "Alappuzha", "Pathanamthitta", "Kollam", "Thiruvananthapuram"];
const FEATURE_NAMES = {
  annual_rainfall: "Annual rainfall", aspect: "Slope direction", clay_content: "Clay content",
  distance_to_water: "Distance from water", elevation: "Elevation", flood_occurrence: "Surface water history",
  land_cover_class: "Land cover", mean_humidity: "Humidity", mean_temperature: "Temperature",
  mean_wind_speed: "Wind speed", ndvi: "Vegetation", organic_carbon: "Soil organic carbon",
  sand_content: "Sand content", slope: "Ground slope", soil_ph: "Soil pH",
  terrain_ruggedness_index: "Terrain roughness", water_content: "Soil water retention",
  flood_level_10yr_m: "10-year flood depth", flood_level_25yr_m: "25-year flood depth",
  flood_level_50yr_m: "50-year flood depth", flood_level_100yr_m: "100-year flood depth",
  flood_level_200yr_m: "200-year flood depth", flood_level_500yr_m: "500-year flood depth",
  gsi_landslide_code: "Landslide mapping", dist_nearest_road: "Road access",
  dist_nearest_highway: "Highway access", dist_nearest_hospital: "Hospital access",
  dist_nearest_school: "School access", dist_nearest_quarry: "Distance from quarry",
  dist_nearest_bus_stop: "Bus access", dist_nearest_railway_station: "Railway access",
  dist_nearest_pharmacy: "Pharmacy access", dist_nearest_shop: "Shop access",
  dist_nearest_bank: "Bank access", dist_nearest_park: "Park access",
  dist_nearest_power_line: "Power-line access", dist_nearest_waste_facility: "Distance from waste facility",
  dist_nearest_industrial: "Distance from industry",
};
const DISTANCES = new Set(Object.keys(FEATURE_NAMES).filter((name) => name.startsWith("dist_")).concat(["distance_to_water"]));
const UNITS = { annual_rainfall: "mm/yr", aspect: "°", clay_content: "%", elevation: "m", flood_occurrence: "%", mean_humidity: "%", mean_temperature: "°C", mean_wind_speed: "m/s", organic_carbon: "g/kg", sand_content: "%", slope: "°", soil_ph: "pH", terrain_ruggedness_index: "m", water_content: "%", flood_level_10yr_m: "m", flood_level_25yr_m: "m", flood_level_50yr_m: "m", flood_level_100yr_m: "m", flood_level_200yr_m: "m", flood_level_500yr_m: "m" };

const fmt = (value, digits = 1) => value == null || Number.isNaN(Number(value)) ? "—" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: digits });
const api = async (path, options = {}) => {
  const response = await fetch(path, options);
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
    search: "M11 4a7 7 0 100 14 7 7 0 000-14zm5 12l5 5",
    mic: "M12 3a3 3 0 00-3 3v5a3 3 0 006 0V6a3 3 0 00-3-3zM5 11a7 7 0 0014 0M12 18v3",
    street: "M4 20V7l8-4 8 4v13M8 20v-8h8v8M9 8h6",
    close: "M5 5l14 14M19 5L5 19",
    arrow: "M5 12h14M14 7l5 5-5 5",
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
    script.onerror = () => reject(new Error("The map could not load."));
    document.head.appendChild(script);
  });
  return mapsPromise;
}

function Progress({ stage }) {
  const steps = [["mapped", "Mapped data"], ["satellite", "Satellite check"], ["explained", "Explanation"]];
  const active = { mapped: 0, satellite: 1, explained: 2 }[stage] ?? -1;
  return <div className="progress">{steps.map(([key, label], index) => <div className={index <= active ? "complete" : index === active + 1 ? "active" : ""} key={key}><i>{index < active ? "✓" : index + 1}</i><span>{label}</span></div>)}</div>;
}

function ModelSignals({ data }) {
  if (!data) return null;
  const scores = data.branch_scores || {}, weights = data.routing_weights || {};
  return <section className="signals">
    <div className="section-heading"><div><h3>Model signals</h3><p>Satellite and mapped-data readings behind this result</p></div><strong>{fmt(scores.fused, 0)}%</strong></div>
    <div className="signal"><span>TerraMind satellite</span><div><i style={{ width: `${scores.terramind || 0}%` }} /></div><b>{scores.terramind == null ? "Loading" : `${fmt(scores.terramind, 0)}%`}</b><small>{fmt(weights.terramind, 0)}% weight</small></div>
    <div className="signal"><span>TabPFN mapped data</span><div><i style={{ width: `${scores.tabpfn || 0}%` }} /></div><b>{scores.tabpfn == null ? "Loading" : `${fmt(scores.tabpfn, 0)}%`}</b><small>{fmt(weights.tabpfn, 0)}% weight</small></div>
  </section>;
}

function ExplainList({ title, items, direction }) {
  return <section className={`explain-list ${direction}`}><h4>{title}</h4>{items.length ? items.map((item) => <div className="explain-item" key={item.feature}>
    <div><strong>{FEATURE_NAMES[item.feature] || item.feature}</strong><span>{valueLabel(item)}</span></div>
    <div className="effect"><i style={{ width: `${Math.min(100, Math.abs(item.contribution) * 8)}%` }} /></div>
    <b>{item.contribution > 0 ? "+" : ""}{fmt(item.contribution)}%</b>
  </div>) : <p>No strong effects in this direction.</p>}</section>;
}

function AssessmentPanel({ report, stage, error, onStreetView, onClear }) {
  const explanation = report?.prediction?.explanation;
  const factors = useMemo(() => explanation?.contributions ? [...explanation.contributions]
    .filter((item) => !(item.feature === "gsi_landslide_code" && Number(item.value) === 0))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 8) : [], [explanation]);
  const helped = factors.filter((item) => item.contribution > 0).slice(0, 4);
  const reduced = factors.filter((item) => item.contribution < 0).slice(0, 4);
  const loading = Boolean(stage && stage !== "complete");
  if (error) return <div className="panel-empty error"><h2>Couldn’t assess this location</h2><p>{error}</p><button onClick={onClear}>Choose another point</button></div>;
  if (!report) return <div className="panel-empty"><span className="empty-icon"><Icon type="point" /></span><h2>Select a location</h2><p>Search for a place, click the map, or draw a site boundary.</p></div>;
  if (report.prediction.status !== "available") return <div className="panel-empty error"><h2>Analysis unavailable</h2><p>{report.prediction.reason}</p></div>;
  const score = report.prediction.suitability_percent;
  return <>
    {loading && <Progress stage={stage} />}
    <section className="score-card">
      <div className="score-top"><div className="score"><strong>{fmt(score, 0)}</strong><span>%</span></div><div><p>{report.outcome}</p><h2>{report.district}</h2><small>{report.location.selection_type === "polygon" ? `${fmt(report.location.area_m2, 0)} m² selected area` : `${Number(report.location.lat).toFixed(5)}, ${Number(report.location.lon).toFixed(5)}`}</small></div></div>
      <div className="score-bar"><i style={{ width: `${score}%` }} /></div>
      <p className="score-summary">{report.reason}</p>
      <button className="outline-action" onClick={onStreetView}><Icon type="street" />Open nearby Street View</button>
    </section>
    {report.location.selection_type === "polygon" && <div className="area-stats"><div><span>Samples</span><strong>{report.prediction.spatial_summary.samples}</strong></div><div><span>Lowest</span><strong>{fmt(report.prediction.spatial_summary.minimum_percent, 0)}%</strong></div><div><span>Highest</span><strong>{fmt(report.prediction.spatial_summary.maximum_percent, 0)}%</strong></div></div>}
    <ModelSignals data={report.prediction.multimodal} />
    <section className="explanation">
      <div className="section-heading"><div><h3>What influenced this score</h3><p>Measured change in the final score</p></div></div>
      {explanation?.status === "ready" ? <><ExplainList title="Helped the score" items={helped} direction="positive" /><ExplainList title="Reduced the score" items={reduced} direction="negative" /></> : <div className="explain-loading"><i /><span>Preparing the simple explanation…</span></div>}
    </section>
  </>;
}

function PreferenceInput({ query, setQuery, recording, voiceStatus, onRecord }) {
  const suggestions = ["Quiet and green", "Near a hospital", "Close to a good road", "Near schools"];
  return <section className="preference-input">
    <label htmlFor="land-request">2. Describe your ideal location <span>Optional</span></label>
    <div className="voice-field"><textarea id="land-request" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="For example: quiet and green, close to a hospital and a good road" /><button className={recording ? "recording" : ""} onClick={onRecord} aria-label={recording ? "Stop recording" : "Describe by voice"}><Icon type="mic" /></button></div>
    {voiceStatus && <p className="voice-status">{voiceStatus}</p>}
    <div className="suggestions">{suggestions.map((suggestion) => <button key={suggestion} onClick={() => setQuery((current) => current ? `${current}, ${suggestion.toLowerCase()}` : suggestion)}>{suggestion}</button>)}</div>
  </section>;
}

function CandidateDetails({ candidate, onAssess }) {
  if (!candidate) return <div className="candidate-empty"><span><Icon type="point" /></span><h3>Results will appear on the map</h3><p>Run the search, then select a result card on the map to inspect that location.</p></div>;
  const evidence = candidate.evidence || {};
  return <section className="candidate-detail">
    <div className="candidate-title"><span>#{candidate.rank}</span><div><p>Selected result</p><h2>{candidate.district}</h2><small>{candidate.lat.toFixed(5)}, {candidate.lon.toFixed(5)}</small></div><strong>{fmt(candidate.overall_fit_percent, 0)}%</strong></div>
    <div className="candidate-scores"><div><strong>{fmt(candidate.suitability_percent, 0)}%</strong><span>Land score</span></div><div><strong>{fmt(candidate.preference_fit_percent, 0)}%</strong><span>Preference match</span></div></div>
    <div className="detail-grid"><div><span>Slope</span><strong>{fmt(evidence.slope)}°</strong></div><div><span>100-year flood depth</span><strong>{fmt(evidence.flood_level_100yr_m)} m</strong></div><div><span>Nearest road</span><strong>{fmt(evidence.road_distance_m, 0)} m</strong></div><div><span>Hospital</span><strong>{evidence.hospital_distance_m >= 1000 ? `${fmt(evidence.hospital_distance_m / 1000)} km` : `${fmt(evidence.hospital_distance_m, 0)} m`}</strong></div><div><span>School</span><strong>{evidence.school_distance_m >= 1000 ? `${fmt(evidence.school_distance_m / 1000)} km` : `${fmt(evidence.school_distance_m, 0)} m`}</strong></div><div><span>Land cover</span><strong>{candidate.apparently_open ? "Apparently open" : "Mixed / built"}</strong></div></div>
    {candidate.advantages.length > 0 && <div className="candidate-reasons">{candidate.advantages.map((item) => <span key={item}>✓ {item}</span>)}</div>}
    <button className="primary-action" onClick={() => onAssess(candidate)}>Assess this exact point <Icon type="arrow" /></button>
  </section>;
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
  const [recording, setRecording] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const mapElement = useRef(null), placeSearchElement = useRef(null), reportElement = useRef(null);
  const map = useRef(null), boundaries = useRef(null), AdvancedMarker = useRef(null), pointMarker = useRef(null), areaPolygon = useRef(null), candidateMarkers = useRef([]), polygonPath = useRef([]);
  const latest = useRef({}), request = useRef(null), media = useRef(null), mediaChunks = useRef([]), streetDialog = useRef(null), streetElement = useRef(null);
  latest.current = { workspace, mode, searchDrawing };

  useEffect(() => { api("/api/config").then(setConfig).catch((reason) => setError(reason.message)); }, []);
  useEffect(() => { if (report && window.innerWidth < 900) reportElement.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [report?.prediction?.analysis_stage]);

  const removeMarker = (marker) => { if (!marker) return; if ("map" in marker) marker.map = null; else marker.setMap?.(null); };
  const clearCandidateMarkers = () => { candidateMarkers.current.forEach(removeMarker); candidateMarkers.current = []; };
  const clearSelection = () => {
    request.current?.abort(); removeMarker(pointMarker.current); pointMarker.current = null;
    areaPolygon.current?.setMap(null); areaPolygon.current = null; polygonPath.current = []; setPolygonPoints(0);
    setReport(null); setStage(""); setError("");
  };

  const runProgressive = async (path, body) => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setReport(null); setError(""); setStage("mapped");
    try {
      const preview = await post(path, { ...body, detail: "preview" }, controller.signal); setReport(preview); setStage("satellite");
      if (path !== "/api/analyze-area") { const full = await post(path, { ...body, detail: "full" }, controller.signal); setReport(full); setStage("explained"); }
      const explained = await post(path, { ...body, detail: "explain" }, controller.signal); setReport(explained); setStage("complete");
    } catch (reason) { if (reason.name !== "AbortError") { setError(reason.message); setStage(""); } }
  };

  const addPointMarker = (lat, lng) => {
    removeMarker(pointMarker.current);
    if (!AdvancedMarker.current || !map.current) return;
    const dot = document.createElement("div"); dot.className = "selected-point"; dot.innerHTML = "<i></i>";
    const Marker = AdvancedMarker.current;
    const marker = new Marker({ map: map.current, position: { lat, lng }, title: "Selected location", gmpClickable: false }); marker.append(dot); pointMarker.current = marker;
  };
  const analyzePoint = (lat, lng) => { areaPolygon.current?.setMap(null); areaPolygon.current = null; addPointMarker(lat, lng); runProgressive("/api/analyze", { lat, lon: lng, radius_m: 150 }); };

  const addPolygonPoint = (lat, lng) => {
    polygonPath.current = [...polygonPath.current, { lat, lng }]; setPolygonPoints(polygonPath.current.length);
    areaPolygon.current?.setMap(null);
    areaPolygon.current = new window.google.maps.Polygon({ map: map.current, paths: polygonPath.current, strokeColor: "#12664c", strokeWeight: 3, fillColor: "#1f8a66", fillOpacity: .16, clickable: false });
  };

  const finishPolygon = () => {
    if (polygonPath.current.length < 3) return;
    const path = [...polygonPath.current];
    areaPolygon.current?.setMap(null);
    areaPolygon.current = new window.google.maps.Polygon({ map: map.current, paths: path, strokeColor: "#12664c", strokeWeight: 3, fillColor: "#1f8a66", fillOpacity: .18, clickable: false });
    const geometry = { type: "Polygon", coordinates: [[...path.map((point) => [point.lng, point.lat]), [path[0].lng, path[0].lat]]] };
    polygonPath.current = []; setPolygonPoints(0);
    if (workspace === "find") { setSearchGeometry(geometry); setSearchDrawing(false); }
    else runProgressive("/api/analyze-area", { geometry });
  };

  useEffect(() => {
    if (!config || map.current || !mapElement.current) return;
    if (!config.google_maps_api_key) { setMapError("Google Maps is not configured."); return; }
    let alive = true;
    loadGoogleMaps(config.google_maps_api_key).then(async () => {
      if (!alive) return;
      const { AdvancedMarkerElement } = await window.google.maps.importLibrary("marker"); AdvancedMarker.current = AdvancedMarkerElement;
      map.current = new window.google.maps.Map(mapElement.current, { center: KERALA_CENTER, zoom: 7, minZoom: 6, maxZoom: 20, mapTypeId: "roadmap", mapId: "DEMO_MAP_ID", streetViewControl: false, fullscreenControl: false, mapTypeControl: false, clickableIcons: false, gestureHandling: "greedy", restriction: { latLngBounds: { north: 13.2, south: 7.8, west: 74.6, east: 78.2 }, strictBounds: false } });
      map.current.addListener("click", (event) => {
        const lat = event.latLng.lat(), lng = event.latLng.lng();
        if (latest.current.workspace === "find") { if (latest.current.searchDrawing) addPolygonPoint(lat, lng); return; }
        if (latest.current.mode === "area") addPolygonPoint(lat, lng); else analyzePoint(lat, lng);
      });
      try {
        const [state, districtData] = await Promise.all([api("/api/layers/kerala"), api("/api/layers/districts")]); boundaries.current = districtData;
        map.current.data.addGeoJson(state); map.current.data.addGeoJson(districtData);
        map.current.data.setStyle((feature) => ({ clickable: false, fillColor: feature.getProperty("name") ? "transparent" : "#12664c", fillOpacity: .02, strokeColor: feature.getProperty("name") ? "#6e8e82" : "#12664c", strokeOpacity: .7, strokeWeight: feature.getProperty("name") ? .7 : 1.5 }));
      } catch (reason) { setMapError(reason.message); }
      try {
        const { PlaceAutocompleteElement } = await window.google.maps.importLibrary("places");
        const autocomplete = new PlaceAutocompleteElement({ placeholder: "Search a place in Kerala" }); autocomplete.setAttribute("aria-label", "Search a place in Kerala"); placeSearchElement.current.replaceChildren(autocomplete);
        autocomplete.addEventListener("gmp-select", async (event) => {
          const place = event.placePrediction.toPlace(); await place.fetchFields({ fields: ["location", "viewport"] }); if (!place.location) return;
          if (place.viewport) map.current.fitBounds(place.viewport); else { map.current.panTo(place.location); map.current.setZoom(16); }
          if (latest.current.workspace === "assess") analyzePoint(place.location.lat(), place.location.lng());
        });
      } catch { setMapError("Place search is temporarily unavailable."); }
    }).catch((reason) => setMapError(reason.message));
    return () => { alive = false; request.current?.abort(); };
  }, [config]);

  useEffect(() => { map.current?.setMapTypeId(mapStyle); }, [mapStyle]);

  const flyDistrict = (name) => {
    setDistrict(name); setSearchGeometry(null); setSearchDrawing(false); areaPolygon.current?.setMap(null); areaPolygon.current = null;
    if (!name || !boundaries.current) { map.current?.setCenter(KERALA_CENTER); map.current?.setZoom(7); return; }
    const feature = boundaries.current.features.find((item) => item.properties.name === name); if (!feature) return;
    const bounds = new window.google.maps.LatLngBounds();
    const walk = (node) => typeof node[0] === "number" ? bounds.extend({ lng: node[0], lat: node[1] }) : node.forEach(walk); walk(feature.geometry.coordinates); map.current.fitBounds(bounds, 42);
  };

  const switchWorkspace = (next) => {
    request.current?.abort(); setWorkspace(next); setError(""); setStage(""); setReport(null); setSearchDrawing(false); polygonPath.current = []; setPolygonPoints(0); removeMarker(pointMarker.current); pointMarker.current = null;
    clearCandidateMarkers(); setSelectedCandidate(null); setSearchResult(null);
  };

  const startSearchArea = () => {
    clearCandidateMarkers(); setSearchResult(null); setSelectedCandidate(null); setSearchGeometry(null); setDistrict(""); setError("");
    areaPolygon.current?.setMap(null); areaPolygon.current = null; polygonPath.current = []; setPolygonPoints(0); setSearchDrawing(true);
  };

  const record = async () => {
    if (recording) { setVoiceStatus("Transcribing locally…"); media.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) => window.MediaRecorder?.isTypeSupported(type));
      mediaChunks.current = []; media.current = preferred ? new MediaRecorder(stream, { mimeType: preferred }) : new MediaRecorder(stream);
      media.current.ondataavailable = (event) => { if (event.data.size) mediaChunks.current.push(event.data); };
      media.current.onstop = async () => {
        setRecording(false); stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(mediaChunks.current, { type: media.current.mimeType || "audio/webm" });
        try { const result = await api("/api/transcribe", { method: "POST", headers: { "Content-Type": blob.type }, body: blob }); if (!result.text) throw new Error("No speech was detected"); setQuery(result.text); setVoiceStatus("Voice added to your request."); }
        catch (reason) { setVoiceStatus(reason.message); }
      };
      media.current.start(); setRecording(true); setVoiceStatus("Listening… tap again when finished");
    } catch (reason) { setVoiceStatus(`Microphone unavailable: ${reason.message}`); }
  };

  const showCandidates = (candidates) => {
    clearCandidateMarkers(); if (!AdvancedMarker.current || !map.current) return;
    const Marker = AdvancedMarker.current;
    const bounds = new window.google.maps.LatLngBounds();
    candidateMarkers.current = candidates.map((candidate) => {
      const position = { lat: candidate.lat, lng: candidate.lon }; bounds.extend(position);
      const card = document.createElement("button"); card.className = "map-result"; card.innerHTML = `<strong>${Math.round(candidate.overall_fit_percent)}%</strong><span>${candidate.district}</span>`;
      const marker = new Marker({ map: map.current, position, title: `${candidate.overall_fit_percent}% match in ${candidate.district}`, gmpClickable: true }); marker.append(card);
      marker.addListener("click", () => { setSelectedCandidate(candidate); map.current.panTo(position); }); return marker;
    });
    if (candidates.length) { map.current.fitBounds(bounds, 80); window.google.maps.event.addListenerOnce(map.current, "idle", () => { if (map.current.getZoom() > 14) map.current.setZoom(14); }); }
  };

  const findLand = async () => {
    setSearching(true); setError(""); setSelectedCandidate(null);
    try {
      const center = map.current?.getCenter();
      const area = searchGeometry ? { geometry: searchGeometry } : district ? { district } : { center_lat: center?.lat() || KERALA_CENTER.lat, center_lon: center?.lng() || KERALA_CENTER.lng, radius_km: 25 };
      const requirements = { avoid_high_flood: true, avoid_high_landslide: true, prefer_open_land: true, max_slope: 30 };
      const result = await post("/api/search", { area, query, requirements, limit: 10 }); setSearchResult(result); showCandidates(result.candidates);
    } catch (reason) { setError(reason.message); }
    finally { setSearching(false); }
  };

  const assessCandidate = (candidate) => {
    switchWorkspace("assess"); setMode("point"); map.current?.panTo({ lat: candidate.lat, lng: candidate.lon }); map.current?.setZoom(17); analyzePoint(candidate.lat, candidate.lon);
  };

  const showStreetView = async () => {
    if (!report || !window.google) return; streetDialog.current?.showModal(); const location = { lat: report.location.lat, lng: report.location.lon };
    try { const result = await new window.google.maps.StreetViewService().getPanorama({ location, radius: 100 }); new window.google.maps.StreetViewPanorama(streetElement.current, { position: result.data.location.latLng, pov: { heading: 0, pitch: 0 }, zoom: 1, addressControl: true }); }
    catch { streetElement.current.innerHTML = '<div class="street-empty"><strong>No Street View nearby</strong><span>Try satellite view for visual context.</span></div>'; }
  };

  const areaLabel = searchGeometry ? "Drawn boundary" : district || "25 km around the visible map centre";
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#">nilam<span>Kerala land intelligence</span></a><nav><button className={workspace === "assess" ? "active" : ""} onClick={() => switchWorkspace("assess")}>Assess a site</button><button className={workspace === "find" ? "active" : ""} onClick={() => switchWorkspace("find")}>Find suitable land</button></nav></header>
    <main>
      <section className="hero"><p>Land decisions, made clearer</p><h1>{workspace === "assess" ? "Understand a specific site." : "Find places that fit your needs."}</h1><span>{workspace === "assess" ? "Click or draw anywhere in Kerala for a detailed suitability report." : "Choose where to search, add preferences if you have them, and explore the best matches on the map."}</span></section>
      <section className="workspace">
        <div className="map-side">
          <div className="map-toolbar">
            <div ref={placeSearchElement} className="place-search"><span>Loading place search…</span></div>
            <select aria-label="Select district" value={district} onChange={(event) => flyDistrict(event.target.value)}><option value="">All Kerala</option>{DISTRICTS.map((name) => <option key={name}>{name}</option>)}</select>
            {workspace === "assess" ? <div className="tool-group"><button className={mode === "point" ? "active" : ""} onClick={() => { clearSelection(); setMode("point"); }}><Icon type="point" />Point</button><button className={mode === "area" ? "active" : ""} onClick={() => { clearSelection(); setMode("area"); }}><Icon type="area" />Draw site</button></div> : <div className="tool-group"><button className={!searchGeometry && !district && !searchDrawing ? "active" : ""} onClick={() => { setSearchGeometry(null); setDistrict(""); setSearchDrawing(false); areaPolygon.current?.setMap(null); }}><Icon type="point" />Map area</button><button className={searchDrawing || searchGeometry ? "active" : ""} onClick={startSearchArea}><Icon type="area" />Draw area</button></div>}
            <div className="tool-group map-style"><button className={mapStyle === "roadmap" ? "active" : ""} onClick={() => setMapStyle("roadmap")}>Map</button><button className={mapStyle === "hybrid" ? "active" : ""} onClick={() => setMapStyle("hybrid")}><Icon type="satellite" />Satellite</button></div>
          </div>
          <div className="map-wrap"><div ref={mapElement} className="map" />
            {!report && !searchResult && !mapError && <div className="map-hint"><Icon type={workspace === "find" ? searchDrawing ? "area" : "search" : mode} /><div><strong>{workspace === "find" ? searchDrawing ? "Click to draw your search boundary" : "Choose the area you want to search" : mode === "area" ? "Click to draw the site boundary" : "Click any point for its suitability"}</strong><span>{workspace === "find" ? searchDrawing ? "Add at least three corners, then finish the area" : "Use a district, the visible map area, or draw a boundary" : "You can also search for an address above"}</span></div></div>}
            {polygonPoints >= 3 && <button className="finish-drawing" onClick={finishPolygon}>Finish boundary · {polygonPoints} points</button>}
            {mapError && <div className="map-message">{mapError}</div>}
          </div>
        </div>
        <aside ref={reportElement} className="side-panel" aria-live="polite">
          {workspace === "assess" ? <AssessmentPanel report={report} stage={stage} error={error} onStreetView={showStreetView} onClear={clearSelection} /> : <div className="find-panel">
            <section className="area-choice"><label>1. Search within</label><div className="area-value"><Icon type="area" /><div><strong>{areaLabel}</strong><span>{searchGeometry ? "Custom area ready" : district ? "District boundary" : "Move the map to change the centre"}</span></div>{searchGeometry && <button onClick={startSearchArea}>Redraw</button>}</div></section>
            <PreferenceInput query={query} setQuery={setQuery} recording={recording} voiceStatus={voiceStatus} onRecord={record} />
            <button className="search-action" disabled={searching || searchDrawing} onClick={findLand}><Icon type="search" />{searching ? "Finding suitable places…" : searchDrawing ? "Finish drawing the area first" : "Find suitable places"}</button>
            {error && <div className="inline-error">{error}</div>}
            {searchResult && <div className="search-summary"><strong>{searchResult.candidates.length} matches on the map</strong><span>Click a result card for location details</span></div>}
            <CandidateDetails candidate={selectedCandidate} onAssess={assessCandidate} />
          </div>}
        </aside>
      </section>
    </main>
    <footer><strong>nilam</strong><span>Kerala land intelligence</span></footer>
    <dialog ref={streetDialog} className="street-dialog"><button className="dialog-close" onClick={() => streetDialog.current?.close()} aria-label="Close"><Icon type="close" /></button><div className="street-head"><h2>Nearby Street View</h2><p>Explore the road-level surroundings of the selected point.</p></div><div ref={streetElement} className="street-view" /></dialog>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
