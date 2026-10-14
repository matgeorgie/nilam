import React, { useEffect, useRef, useState } from "react";

const metres = (value) => value == null ? "Not mapped" : value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${Math.round(value)} m`;
const radians = (value) => value * Math.PI / 180;
const distance = (from, to) => {
  const dLat = radians(to.lat - from.lat), dLon = radians(to.lng - from.lng);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(radians(from.lat)) * Math.cos(radians(to.lat)) * Math.sin(dLon / 2) ** 2;
  return 6371008.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};
const bearing = (from, to) => {
  const dLon = radians(to.lng - from.lng), a = radians(from.lat), b = radians(to.lat);
  return (Math.atan2(Math.sin(dLon) * Math.cos(b), Math.cos(a) * Math.sin(b) - Math.sin(a) * Math.cos(b) * Math.cos(dLon)) * 180 / Math.PI + 360) % 360;
};

function SiteImagery({ candidate }) {
  const satellite = useRef(null), street = useRef(null);
  const [view, setView] = useState("loading");
  const [streetDistance, setStreetDistance] = useState(null);
  useEffect(() => {
    const google = window.google;
    if (!google?.maps || !satellite.current || !street.current) { setView("satellite"); return; }
    let active = true;
    const target = { lat: candidate.lat, lng: candidate.lon };
    new google.maps.Map(satellite.current, {
      center: target, zoom: 18, mapTypeId: "satellite", disableDefaultUI: true,
      clickableIcons: false, gestureHandling: "none", keyboardShortcuts: false,
    });
    setView("loading");
    new google.maps.StreetViewService().getPanorama({
      location: target, radius: 250, preference: google.maps.StreetViewPreference.NEAREST,
      sources: [google.maps.StreetViewSource.OUTDOOR],
    }).then((result) => {
      if (!active) return;
      const location = result.data.location.latLng;
      const camera = { lat: location.lat(), lng: location.lng() };
      const away = distance(camera, target);
      if (away > 250) { setView("satellite"); return; }
      new google.maps.StreetViewPanorama(street.current, {
        pano: result.data.location.pano,
        pov: { heading: bearing(camera, target), pitch: 0 }, zoom: 0,
        disableDefaultUI: true, clickToGo: false, linksControl: false,
        addressControl: false, motionTracking: false, showRoadLabels: false,
      });
      setStreetDistance(away);
      setView("street");
    }).catch(() => { if (active) setView("satellite"); });
    return () => { active = false; };
  }, [candidate.point_id, candidate.lat, candidate.lon]);
  return <div className={`comparison-imagery ${view}`}>
    <div ref={street} className="comparison-street" aria-hidden="true" />
    <div ref={satellite} className="comparison-satellite" aria-hidden="true" />
    <span className="comparison-image-label">{view === "street" ? `Street View nearby · ${metres(streetDistance)} away` : view === "loading" ? "Checking Street View…" : "Satellite view · no nearby road image"}</span>
  </div>;
}

function ComparisonSite({ candidate, side, onVote, busy }) {
  const evidence = candidate.evidence || {};
  return <article className="comparison-site">
    <SiteImagery candidate={candidate} />
    <div className="comparison-site-body">
      <div className="comparison-site-title"><div><h3>{candidate.district}</h3><small>{candidate.lat.toFixed(5)}, {candidate.lon.toFixed(5)}</small></div><strong>{Math.round(candidate.suitability_percent)}%</strong></div>
      {candidate.community_votes > 0 && <p className="comparison-score-note">Original model {Math.round(candidate.original_suitability_percent)}% · community {candidate.preference_adjustment_points >= 0 ? "+" : ""}{candidate.preference_adjustment_points} points</p>}
      <div className="comparison-facts">
        <span><b>{Math.round(candidate.flat_land_percent)}%</b> flat-ground signal</span>
        <span><b>{Math.round(candidate.open_land_percent)}%</b> open-land signal</span>
        <span><b>{metres(evidence.road_distance_m)}</b> nearest mapped road</span>
        <span><b>{metres(evidence.hospital_distance_m)}</b> nearest hospital</span>
      </div>
      <button className="comparison-choose" disabled={busy} onClick={() => onVote(side)}>I prefer this site</button>
    </div>
  </article>;
}

export default function ComparisonDialog({ dialogRef, pair, status, busy, error, feedback, evaluation, onVote, onClose }) {
  return <dialog ref={dialogRef} className="comparison-dialog" onClose={onClose} aria-labelledby="comparison-title">
    <header className="comparison-head"><div><h2 id="comparison-title">Which place feels more like home?</h2><p>Compare two screened sites. Your choice teaches Nilam’s local community ranking.</p></div><button className="comparison-close" onClick={() => dialogRef.current?.close()}>Close</button></header>
    {feedback && <p className="comparison-feedback" role="status">{feedback}</p>}
    {error && <p className="comparison-error" role="alert">{error}</p>}
    {status === "loading" && <div className="comparison-state">Choosing two useful sites to compare…</div>}
    {status === "exhausted" && <div className="comparison-state"><strong>You’ve compared the available pairs here.</strong><span>Move the search centre or radius to explore another area.</span></div>}
    {pair && <><div className="comparison-sites">
      <ComparisonSite key={`${pair.pair_id}-left`} candidate={pair.left} side="left" onVote={onVote} busy={busy} />
      <ComparisonSite key={`${pair.pair_id}-right`} candidate={pair.right} side="right" onVote={onVote} busy={busy} />
    </div><div className="comparison-secondary"><button disabled={busy} onClick={() => onVote("tie")}>Both are equally appealing</button><button disabled={busy} onClick={() => onVote("skip")}>Skip this pair</button></div></>}
    <footer className="comparison-foot"><span>Street View shows a nearby road and may not show the site itself. Satellite imagery is visual context.</span><strong>{pair?.community_votes ?? 0} community votes</strong></footer>
    {evaluation?.holdout_votes >= 10 && <p className="comparison-evaluation">Held-out pair accuracy: learned {Math.round((evaluation.learned.pairwise_accuracy || 0) * 100)}% · original ranking {Math.round((evaluation.static_ranking.pairwise_accuracy || 0) * 100)}% ({evaluation.heldout_strict_choices} choices)</p>}
  </dialog>;
}
