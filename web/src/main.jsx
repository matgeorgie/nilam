import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import "./style.css";

const districtNames = [
  "Kasaragod",
  "Kannur",
  "Wayanad",
  "Kozhikode",
  "Malappuram",
  "Palakkad",
  "Thrissur",
  "Ernakulam",
  "Idukki",
  "Kottayam",
  "Alappuzha",
  "Pathanamthitta",
  "Kollam",
  "Thiruvananthapuram",
];
const titles = {
  elevation: "Elevation",
  slope: "Ground slope",
  northness: "Slope orientation · north",
  eastness: "Slope orientation · east",
  relief_300m: "Terrain variation",
  rainfall_annual: "Historical annual rainfall",
};
const modelNames = {
  extra_trees: "ExtraTrees baseline",
  feature_transformer: "Feature Transformer",
  tabpfn: "TabPFN 3.5 Fast",
};
const fmt = (value, decimals = 1) =>
  value == null
    ? "Not available"
    : Number(value).toLocaleString("en-IN", {
        maximumFractionDigits: decimals,
      });
async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

function App() {
  const [config, setConfig] = useState(null),
    [report, setReport] = useState(null),
    [saved, setSaved] = useState(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [mapError, setMapError] = useState(""),
    [district, setDistrict] = useState(""),
    [layer, setLayer] = useState(true),
    [model, setModel] = useState("extra_trees"),
    [radius, setRadius] = useState(150),
    [coordinates, setCoordinates] = useState({ lat: "9.9312", lon: "76.2673" }),
    [tab, setTab] = useState("overview");
  const container = useRef(),
    map = useRef(),
    marker = useRef(),
    dialog = useRef(),
    districts = useRef(),
    latest = useRef(),
    requestId = useRef(0);
  latest.current = { model, radius };
  useEffect(() => {
    request("/api/config")
      .then(setConfig)
      .catch((e) => setError(e.message));
  }, []);
  async function analyze(lon, lat) {
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    setReport(null);
    setCoordinates({ lat: lat.toFixed(5), lon: lon.toFixed(5) });
    if (map.current) {
      if (!marker.current)
        marker.current = new mapboxgl.Marker({ color: "#b77948" });
      marker.current.setLngLat([lon, lat]).addTo(map.current);
    }
    try {
      const result = await request("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat,
          lon,
          radius_m: latest.current.radius,
          model: latest.current.model,
        }),
      });
      if (id !== requestId.current) return;
      setReport(result);
      map.current
        ?.getSource("selection")
        ?.setData({ type: "Feature", geometry: result.area, properties: {} });
    } catch (e) {
      if (id === requestId.current)
        setError(
          typeof e.message === "string"
            ? e.message
            : "Please check the selected coordinates",
        );
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }
  useEffect(() => {
    if (!config || map.current || !container.current) return;
    if (!config.mapbox_token) {
      setMapError(
        "Mapbox token is not configured. You can still enter coordinates below.",
      );
      return;
    }
    mapboxgl.accessToken = config.mapbox_token;
    const m = new mapboxgl.Map({
      container: container.current,
      style: "mapbox://styles/mapbox/light-v11",
      center: [76.25, 10.5],
      zoom: 6.6,
      minZoom: 5,
      maxZoom: 18,
      maxBounds: [
        [73.7, 7.5],
        [79, 14],
      ],
      attributionControl: true,
    });
    map.current = m;
    m.addControl(
      new mapboxgl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    m.on("error", () =>
      setMapError(
        "Some map tiles could not load. Coordinate search remains available.",
      ),
    );
    m.on("click", (e) => analyze(e.lngLat.lng, e.lngLat.lat));
    m.on("load", async () => {
      try {
        const [state, ds] = await Promise.all([
          request("/api/layers/kerala"),
          request("/api/layers/districts"),
        ]);
        districts.current = ds;
        m.addSource("state", { type: "geojson", data: state });
        m.addLayer({
          id: "state-fill",
          type: "fill",
          source: "state",
          paint: { "fill-color": "#457d62", "fill-opacity": 0.09 },
        });
        m.addLayer({
          id: "state-line",
          type: "line",
          source: "state",
          paint: { "line-color": "#173e35", "line-width": 1.6 },
        });
        m.addSource("districts", { type: "geojson", data: ds });
        m.addLayer({
          id: "district-lines",
          type: "line",
          source: "districts",
          paint: {
            "line-color": "#527367",
            "line-width": 0.7,
            "line-dasharray": [3, 3],
          },
        });
        m.addLayer({
          id: "district-labels",
          type: "symbol",
          source: "districts",
          layout: {
            "text-field": ["get", "name"],
            "text-size": 11,
            "text-font": ["DIN Pro Medium", "Arial Unicode MS Regular"],
          },
          paint: {
            "text-color": "#25483c",
            "text-halo-color": "#f6f4ed",
            "text-halo-width": 1.8,
          },
        });
        m.addSource("selection", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        m.addLayer({
          id: "selection-fill",
          type: "fill",
          source: "selection",
          paint: { "fill-color": "#b77948", "fill-opacity": 0.13 },
        });
        m.addLayer({
          id: "selection-outline",
          type: "line",
          source: "selection",
          paint: { "line-color": "#8d5a31", "line-width": 2 },
        });
        const hazards = await request("/api/layers/hazards");
        m.addSource("hazards", { type: "geojson", data: hazards });
        m.addLayer(
          {
            id: "hazards-fill",
            type: "fill",
            source: "hazards",
            paint: {
              "fill-color": [
                "match",
                ["get", "source_label"],
                "High Hazard Zone",
                "#aa584b",
                "Medium Hazard Zone",
                "#c39950",
                "Low Hazard Zone",
                "#6c9270",
                "Waterbody",
                "#3f859d",
                "#739ba8",
              ],
              "fill-opacity": 0.32,
            },
          },
          "state-line",
        );
      } catch (e) {
        setMapError(e.message);
      }
    });
    return () => {
      m.remove();
      map.current = null;
    };
  }, [config]);
  function selectDistrict(value) {
    setDistrict(value);
    if (!value || !districts.current || !map.current) return;
    const feature = districts.current.features.find(
      (f) => f.properties.name === value,
    );
    if (!feature) return;
    const bounds = new mapboxgl.LngLatBounds();
    function scan(a) {
      if (typeof a[0] === "number") bounds.extend(a);
      else a.forEach(scan);
    }
    scan(feature.geometry.coordinates);
    map.current.fitBounds(bounds, { padding: 55, duration: 700 });
  }
  function toggleLayers() {
    const value = !layer;
    setLayer(value);
    if (map.current?.getLayer("hazards-fill"))
      map.current.setLayoutProperty(
        "hazards-fill",
        "visibility",
        value ? "visible" : "none",
      );
  }
  function submit(e) {
    e.preventDefault();
    const lon = Number(coordinates.lon),
      lat = Number(coordinates.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      setError("Enter valid coordinates");
      return;
    }
    map.current?.flyTo({ center: [lon, lat], zoom: 13 });
    analyze(lon, lat);
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `nilam-${report.location.lat}-${report.location.lon}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  const evaluation = config?.evaluation;
  return (
    <>
      <header className="masthead">
        <a href="/" className="brand" aria-label="Nilam home">
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <path d="M5 28 14 8l7 15 10-18M5 33h26" />
          </svg>
          <span>
            nilam<span className="brand-ml">നിലം</span>
          </span>
        </a>
        <div className="scope">
          <span className="dot" />
          KERALA LAND OBSERVATORY <span className="scope-divider">/</span>{" "}
          RESEARCH EDITION
        </div>
        <button
          className="text-button"
          onClick={() => dialog.current.showModal()}
        >
          Methods & models <span aria-hidden="true">↗</span>
        </button>
      </header>
      <main>
        <section className="intro">
          <div>
            <p className="eyebrow">A CLOSER LOOK, BEFORE YOU BUILD</p>
            <h1>
              Know the land.
              <br />
              <em>See the evidence.</em>
            </h1>
          </div>
          <div className="intro-note">
            <p>
              From the coast to the Western Ghats.
              <br />
              Explore the conditions around a place
              <br />
              you could someday call home.
            </p>
            <span>
              14 DISTRICTS <span className="tiny-separator">·</span> ONE
              CONNECTED LANDSCAPE
            </span>
          </div>
        </section>
        <section className="workspace" aria-label="Land assessment workspace">
          <div className="map-column">
            <div className="map-tools">
              <label className="district-select">
                <span className="sr-only">Explore a district</span>
                <select
                  value={district}
                  onChange={(e) => selectDistrict(e.target.value)}
                >
                  <option value="">Explore all Kerala</option>
                  {districtNames.map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
              <button
                className={layer ? "layer-button active" : "layer-button"}
                aria-pressed={layer}
                onClick={toggleLayers}
              >
                <span aria-hidden="true">▱</span> Hazard layers
              </button>
            </div>
            <div className="map-frame">
              <div
                ref={container}
                className="map"
                aria-label="Interactive map of Kerala. Click to assess a location; coordinates form is available below."
              />
              <div className="map-caption">
                <span className="map-cross">+</span>
                <div>
                  <strong>Choose a place to begin</strong>
                  <span>Click anywhere inside Kerala</span>
                </div>
              </div>
              {mapError && (
                <div className="map-error" role="status">
                  {mapError}
                </div>
              )}
              <div className="map-legend">
                <span>
                  <i className="flood" />
                  Flood plain / water
                </span>
                <span>
                  <i className="landslide" />
                  High landslide zone
                </span>
                <small>Historical KSDMA reference layers</small>
              </div>
            </div>
            <form className="coordinate-form" onSubmit={submit}>
              <div className="coordinate-label">
                OR ENTER
                <br />
                <strong>Coordinates</strong>
              </div>
              <label>
                LATITUDE
                <input
                  type="number"
                  required
                  step="any"
                  min="8"
                  max="13"
                  value={coordinates.lat}
                  onChange={(e) =>
                    setCoordinates({ ...coordinates, lat: e.target.value })
                  }
                />
              </label>
              <label>
                LONGITUDE
                <input
                  type="number"
                  required
                  step="any"
                  min="74"
                  max="78"
                  value={coordinates.lon}
                  onChange={(e) =>
                    setCoordinates({ ...coordinates, lon: e.target.value })
                  }
                />
              </label>
              <button className="primary" type="submit" disabled={loading}>
                {loading ? "Reading…" : "Assess land ↗"}
              </button>
            </form>
            <div className="map-footnote">
              <span>© OpenStreetMap contributors · ODbL</span>
              <span>Point selection · neighbourhood screening</span>
            </div>
          </div>
          <aside className="report-column" aria-label="Assessment results">
            <div className="report-heading">
              <span className="eyebrow">FIELD NOTES</span>
              <span className="small-caps">
                {report ? report.district : "YOUR SELECTED LOCATION"}
              </span>
            </div>
            <div className="assessment-controls">
              <label>
                Assessment radius
                <select
                  value={radius}
                  onChange={(e) => setRadius(Number(e.target.value))}
                >
                  <option value="50">50 metres</option>
                  <option value="150">150 metres</option>
                  <option value="300">300 metres</option>
                  <option value="500">500 metres</option>
                </select>
              </label>
              <label>
                Research model
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                >
                  <option value="extra_trees">ExtraTrees</option>
                  <option
                    value="feature_transformer"
                    disabled={!evaluation?.models.feature_transformer}
                  >
                    Feature Transformer
                  </option>
                  <option
                    value="tabpfn"
                    disabled={!evaluation?.models.tabpfn_3_5_fast}
                  >
                    TabPFN 3.5 Fast
                  </option>
                </select>
              </label>
            </div>
            <p className="controls-note">
              Changes apply on your next assessment.
            </p>
            {loading ? (
              <div className="empty-state" role="status">
                <div className="scan-indicator" />
                <p className="eyebrow">READING THE LAND</p>
                <h2>Connecting the evidence.</h2>
                <p>
                  Checking mapped hazards, nearby facilities and Earth Engine
                  measurements. The first assessment can take a minute.
                </p>
              </div>
            ) : error ? (
              <div className="empty-state error" role="alert">
                <h2>Let’s check that location.</h2>
                <p>{error}</p>
              </div>
            ) : !report ? (
              <div className="empty-state">
                <div className="contour-mark" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                  <b>+</b>
                </div>
                <p className="eyebrow">EVERY PLACE HAS A STORY</p>
                <h2>
                  Start with a point
                  <br />
                  on the map.
                </h2>
                <p>
                  We’ll bring together the terrain, mapped hazards and everyday
                  connections—and show what remains unknown.
                </p>
                <div className="empty-index">
                  <span>
                    01 <b>Read the landscape</b>
                  </span>
                  <span>
                    02 <b>Understand the model</b>
                  </span>
                  <span>
                    03 <b>Plan the next checks</b>
                  </span>
                </div>
              </div>
            ) : (
              <>
                <div
                  className={
                    "verdict " +
                    (report.outcome === "High concern" ? "concern" : "")
                  }
                >
                  <p className="eyebrow">
                    PRELIMINARY SCREENING · {report.location.radius_m} M RADIUS
                  </p>
                  <h2>{report.outcome}</h2>
                  <p>{report.reason}</p>
                  <span className="coordinate-stamp">
                    {report.location.lat.toFixed(5)}° N &nbsp;{" "}
                    {report.location.lon.toFixed(5)}° E
                  </span>
                </div>
                <nav className="report-tabs" aria-label="Report sections">
                  {[
                    ["overview", "Evidence"],
                    ["explain", "Model & why"],
                    ["next", "Next checks"],
                  ].map(([id, label]) => (
                    <button
                      key={id}
                      className={tab === id ? "selected" : ""}
                      aria-pressed={tab === id}
                      onClick={() => setTab(id)}
                    >
                      {label}
                    </button>
                  ))}
                </nav>
                <div className="report-content">
                  {tab === "overview" && (
                    <>
                      <h3>
                        Mapped conditions <span>01</span>
                      </h3>
                      {report.hazards.length ? (
                        report.hazards.map((h) => (
                          <div className="hazard-row" key={h.label}>
                            <div>
                              <strong>{h.label}</strong>
                              <small>
                                {h.vintage} ·{" "}
                                {h.point_intersection
                                  ? "At selected point"
                                  : "Within selected radius"}
                              </small>
                            </div>
                            <span>
                              {fmt(h.area_percent)}
                              <small>% of area</small>
                            </span>
                          </div>
                        ))
                      ) : (
                        <p className="unknown-note">
                          No reference polygon intersects this area. Unmapped
                          does not mean safe.
                        </p>
                      )}
                      <h3>
                        Reading the terrain <span>02</span>
                      </h3>
                      <div className="terrain-grid">
                        {report.terrain
                          .filter(
                            (x) =>
                              !["northness", "eastness"].includes(x.feature),
                          )
                          .map((x) => (
                            <div key={x.feature}>
                              <span>{titles[x.feature]}</span>
                              <strong>
                                {fmt(x.value)}{" "}
                                <small>{x.value == null ? "" : x.unit}</small>
                              </strong>
                              <small>
                                {x.resolution_m >= 1000
                                  ? `${fmt(x.resolution_m / 1000)} km`
                                  : `${x.resolution_m} m`}{" "}
                                source resolution · {x.vintage}
                              </small>
                            </div>
                          ))}
                      </div>
                      <h3>
                        Everyday connections <span>03</span>
                      </h3>
                      <p className="section-note">
                        Nearest mapped points · straight-line distances
                      </p>
                      {report.nearby.map((p) => (
                        <div className="amenity-row" key={p.kind}>
                          <div>
                            <strong>{p.kind.replace("_", " ")}</strong>
                            <small>{p.name}</small>
                          </div>
                          <span>
                            {p.distance_m >= 1000
                              ? `${fmt(p.distance_m / 1000)} km`
                              : `${p.distance_m} m`}
                          </span>
                        </div>
                      ))}
                      {report.google_places?.length > 0 && (
                        <div className="google-places">
                          <div className="google-attribution" translate="no">
                            Google Maps
                          </div>
                          {report.google_places.map((p) => (
                            <div className="amenity-row" key={p.place_id}>
                              <div>
                                <strong>{p.kind}</strong>
                                <small>{p.name}</small>
                              </div>
                              {p.google_maps_uri && (
                                <a
                                  href={p.google_maps_uri}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  View ↗
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      <p className="unknown-note">
                        Nearest mapped road: {fmt(report.road.distance_m, 0)} m.
                        Road proximity does not establish legal access. OSM
                        point coverage may omit facilities.
                      </p>
                    </>
                  )}
                  {tab === "explain" && (
                    <>
                      <h3>
                        What the model sees <span>04</span>
                      </h3>
                      {report.prediction.status === "available" ? (
                        <>
                          <p className="section-note">
                            {modelNames[report.prediction.model]} · historical
                            landslide map classes
                          </p>
                          <div className="probabilities">
                            {report.prediction.class_scores.map((v, i) => (
                              <div
                                key={i}
                                className={
                                  i === report.prediction.class_index
                                    ? "strongest"
                                    : ""
                                }
                              >
                                <span>{report.prediction.class_names[i]}</span>
                                <strong>
                                  {fmt(v * 100, 0)}
                                  <small>%</small>
                                </strong>
                                <div style={{ width: `${v * 100}%` }} />
                              </div>
                            ))}
                          </div>
                          <p className="unknown-note">
                            These are model class scores—not the probability of
                            a landslide or permission to build.
                          </p>
                          <h3>Why this prediction?</h3>
                          <p className="section-note">
                            Effect on the model’s{" "}
                            <strong>high-susceptibility</strong> score. Green
                            lowers it; rust raises it.
                          </p>
                          <div className="contributions">
                            {[...report.prediction.explanation.contributions]
                              .sort(
                                (a, b) =>
                                  Math.abs(b.contribution) -
                                  Math.abs(a.contribution),
                              )
                              .map((c) => (
                                <div key={c.feature}>
                                  <div>
                                    <span>{titles[c.feature]}</span>
                                    <strong>
                                      {c.contribution > 0 ? "+" : ""}
                                      {fmt(c.contribution * 100)} pp
                                    </strong>
                                  </div>
                                  <div className="bar-track">
                                    <i
                                      className={
                                        c.contribution > 0
                                          ? "positive"
                                          : "negative"
                                      }
                                      style={{
                                        width: `${Math.min(100, Math.abs(c.contribution) * 200)}%`,
                                      }}
                                    />
                                  </div>
                                </div>
                              ))}
                          </div>
                          <p className="section-note">
                            Reference score{" "}
                            {fmt(
                              report.prediction.explanation.base_value * 100,
                            )}
                            % → selected location{" "}
                            {fmt(
                              report.prediction.explanation.output_value * 100,
                            )}
                            %.
                          </p>
                          <details>
                            <summary>Explanation method & limits</summary>
                            <p>
                              {report.prediction.explanation.method}.{" "}
                              {report.prediction.explanation.meaning}{" "}
                              {report.prediction.limitation}
                            </p>
                          </details>
                        </>
                      ) : (
                        <div className="unknown-note">
                          <strong>
                            {report.prediction.status === "abstained"
                              ? "The model abstained."
                              : "Prediction not available yet."}
                          </strong>
                          <p>{report.prediction.reason}</p>
                          {report.prediction.features && (
                            <p>
                              Outside observed training range:{" "}
                              {report.prediction.features
                                .map((f) => titles[f])
                                .join(", ")}
                              .
                            </p>
                          )}
                        </div>
                      )}
                      <button
                        className="inline-link"
                        onClick={() => dialog.current.showModal()}
                      >
                        Inspect training & validation ↗
                      </button>
                    </>
                  )}
                  {tab === "next" && (
                    <>
                      <h3>
                        What we cannot establish <span>05</span>
                      </h3>
                      <p className="section-note">
                        These checks matter even when the mapped conditions look
                        favourable.
                      </p>
                      <ul className="check-list">
                        {report.unknowns.map((x) => (
                          <li key={x}>
                            <span>?</span>
                            {x}
                          </li>
                        ))}
                      </ul>
                      <h3>Take the next step</h3>
                      <ol className="next-list">
                        {report.next_steps.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ol>
                      <p className="unknown-note">
                        A satellite pixel is not a soil test. This is a research
                        screening report, not a cadastral or engineering
                        assessment.
                      </p>
                    </>
                  )}
                </div>
                <div className="report-actions">
                  <button className="primary" onClick={download}>
                    Save evidence report ↓
                  </button>
                  <button
                    className="text-button"
                    onClick={() => setSaved(report)}
                  >
                    Pin for comparison
                  </button>
                </div>
              </>
            )}
          </aside>
        </section>
        {saved && (
          <section className="comparison">
            <div>
              <p className="eyebrow">PINNED COMPARISON</p>
              <h2>Two places. Different evidence.</h2>
            </div>
            <div>
              <strong>{saved.district}</strong>
              <p>
                {saved.location.lat.toFixed(4)}, {saved.location.lon.toFixed(4)}
              </p>
              <span>{saved.outcome}</span>
            </div>
            <div>
              <strong>{report?.district || "Select another location"}</strong>
              <p>
                {report
                  ? `${report.location.lat.toFixed(4)}, ${report.location.lon.toFixed(4)}`
                  : "Click the map to compare"}
              </p>
              <span>{report?.outcome}</span>
            </div>
            <button
              className="text-button"
              onClick={() => setSaved(null)}
              aria-label="Clear comparison"
            >
              Clear ×
            </button>
          </section>
        )}
        <section className="principles">
          <div>
            <span>01 / TRACEABLE</span>
            <h3>Evidence, with its origin.</h3>
            <p>
              Every layer has a source and a scale. Historical maps stay visibly
              historical.
            </p>
          </div>
          <div>
            <span>02 / EXPLAINABLE</span>
            <h3>Look inside the prediction.</h3>
            <p>
              See which measured features move the model’s output, and in which
              direction.
            </p>
          </div>
          <div>
            <span>03 / HONEST</span>
            <h3>Unknown is an answer.</h3>
            <p>
              Missing evidence and unfamiliar terrain are reasons to investigate
              further.
            </p>
          </div>
        </section>
      </main>
      <footer>
        <a className="footer-brand" href="/">
          nilam.
        </a>
        <p>Built for Kerala. Grounded in evidence.</p>
        <span>RESEARCH PROTOTYPE · NOT CONSTRUCTION CLEARANCE</span>
      </footer>
      <dialog ref={dialog} className="methods">
        <button
          className="dialog-close"
          onClick={() => dialog.current.close()}
          aria-label="Close methods"
        >
          ×
        </button>
        <p className="eyebrow">THE RESEARCH BEHIND NILAM</p>
        <h2>Methods, not mystery.</h2>
        <p>
          We train models to reproduce historical KSDMA landslide susceptibility
          classes from Earth Engine terrain and rainfall. This is an initial
          research task, distinct from validating whether a home can safely be
          built.
        </p>
        {evaluation ? (
          <>
            <div className="research-stats">
              <div>
                <strong>{evaluation.rows}</strong>
                <span>measured samples</span>
              </div>
              <div>
                <strong>{evaluation.features.length}</strong>
                <span>physical predictors</span>
              </div>
              <div>
                <strong>{Object.keys(evaluation.models).length}</strong>
                <span>model experiments</span>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <caption>Held-out evaluation · macro F1</caption>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Validation</th>
                    <th>Test</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(evaluation.models).map(([name, result]) => (
                    <tr key={name}>
                      <td>{name.replaceAll("_", " ")}</td>
                      <td>{fmt(result.validation.macro_f1, 3)}</td>
                      <td>{fmt(result.test.macro_f1, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              {evaluation.split}. {evaluation.sampling_warning}.
            </p>
            <details>
              <summary>Reproducibility details</summary>
              <p>
                Dataset fingerprint: <code>{evaluation.dataset_sha256}</code>
              </p>
              {Object.entries(evaluation.models).map(([name, result]) => (
                <p key={name}>
                  <strong>{name}</strong>: {result.training}
                </p>
              ))}
            </details>
          </>
        ) : (
          <p className="unknown-note">
            Training is in progress. No performance claims are shown until the
            evaluation artifact exists.
          </p>
        )}
        <h3>Source ledger</h3>
        <ul className="sources">
          <li>
            <a
              href="https://sdma.kerala.gov.in/maps/"
              target="_blank"
              rel="noreferrer"
            >
              KSDMA / NCESS historical hazard maps ↗
            </a>
            <span>
              Source page attributes the maps to 2010. Missing coverage is not a
              negative label.
            </span>
          </li>
          <li>
            <a
              href="https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003"
              target="_blank"
              rel="noreferrer"
            >
              NASA / USGS SRTM ↗
            </a>
            <span>
              30 m elevation, acquired in 2000. Derived slope and local terrain
              variation.
            </span>
          </li>
          <li>
            <a
              href="https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY"
              target="_blank"
              rel="noreferrer"
            >
              CHIRPS rainfall ↗
            </a>
            <span>
              Approximately 5.6 km source cells. 2000–2009 average annual
              totals.
            </span>
          </li>
          <li>
            <a
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noreferrer"
            >
              OpenStreetMap contributors ↗
            </a>
            <span>
              Local PBF extract. Mapped roads and point amenities; incomplete
              coverage is possible.
            </span>
          </li>
        </ul>
        <p className="unknown-note">
          Next research milestone: independent flood/landslide event labels,
          spatially buffered and district-held-out testing, probability
          calibration and expert-reviewed suitability labels.
        </p>
      </dialog>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
