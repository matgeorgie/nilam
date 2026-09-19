"""Local research API. Bind to localhost; no production security claims."""
from __future__ import annotations
import json
import os
from pathlib import Path
from functools import lru_cache
from threading import Lock
import geopandas as gpd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping
from kerala_land_lab.earth import load_env, initialize, point_features, FEATURES, CATALOG
from kerala_land_lab.places import nearby_places

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/processed'
load_env()
app=FastAPI(title='Nilam · Kerala Land Lab',version='0.1.0')
earth_lock=Lock();model_lock=Lock();earth_ready=False


@lru_cache(maxsize=1)
def geography():
    return {'state':gpd.read_file(DATA/'kerala.geojson').to_crs(32643),
            'districts':gpd.read_file(DATA/'districts.geojson').to_crs(32643),
            'hazards':gpd.read_file(DATA/'hazards.gpkg').to_crs(32643),
            'amenities':gpd.read_file(DATA/'amenities.gpkg').to_crs(32643),
            'roads':gpd.read_file(DATA/'roads.gpkg').to_crs(32643)}


class Location(BaseModel):
    lat:float=Field(ge=8,le=13)
    lon:float=Field(ge=74,le=78)
    radius_m:int=Field(default=150,ge=50,le=500)
    model:str=Field(default='extra_trees',pattern='^(extra_trees|feature_transformer|tabpfn)$')


@app.get('/api/config')
def config():
    evaluation=ROOT/'models/evaluation.json'
    return {'mapbox_token':os.environ.get('MAPBOX_PUBLIC_TOKEN',''),
            'evaluation':json.loads(evaluation.read_text()) if evaluation.exists() else None,
            'earth_project_configured':bool(os.environ.get('PROJECT_ID')),
            'google_places_configured':bool(os.environ.get('GOOGLE_PLACES_API_KEY')),
            'research_status':'Historical map screening; construction suitability not validated'}


@app.get('/api/layers/{name}')
def layer(name:str):
    if name not in {'districts','kerala','hazards'}:raise HTTPException(404,'Layer not found')
    if name!='hazards':return json.loads((DATA/f'{name}.geojson').read_text())
    return hazard_layer()


@lru_cache(maxsize=1)
def hazard_layer():
    frame=geography()['hazards'][['source_label','geometry']].copy()
    frame.geometry=frame.geometry.simplify(45,preserve_topology=True)
    return json.loads(frame.to_crs(4326).to_json())


def intersecting(frame,geometry):
    return frame.iloc[frame.sindex.query(geometry,predicate='intersects')]


@lru_cache(maxsize=256)
def measurements(lon,lat):
    global earth_ready
    with earth_lock:
        if not earth_ready:initialize();earth_ready=True
        return point_features(lon,lat)


def prediction(values,selected):
    if any(values.get(name) is None for name in FEATURES):
        return {'status':'unavailable','reason':'Required Earth Engine measurements are missing'}
    import joblib
    import shap
    file=ROOT/'models/baseline.joblib'
    if not file.exists():return {'status':'unavailable','reason':'Training has not finished'}
    bundle=load_baseline()
    x=np.array([[values[name] for name in FEATURES]],dtype=np.float32)
    outside=[name for i,name in enumerate(FEATURES) if x[0,i]<bundle['train_min'][i] or x[0,i]>bundle['train_max'][i]]
    if outside:
        return {'status':'abstained','reason':'Outside the pilot training feature range','features':outside}
    with model_lock:
        if selected=='feature_transformer':
            import torch
            from kerala_land_lab.model import FeatureTransformer
            scaler=joblib.load(ROOT/'models/transformer_scaler.joblib')
            network=FeatureTransformer(len(FEATURES));network.load_state_dict(torch.load(ROOT/'models/feature_transformer.pt',map_location='cpu',weights_only=True));network.eval()
            def predict(a):
                with torch.no_grad():return torch.softmax(network(torch.tensor(scaler.transform(a),dtype=torch.float32)),dim=1).numpy()
            probs=predict(x)[0]
            exp=shap.Explainer(predict,bundle['background'][:8],algorithm='permutation',seed=42)(x,max_evals=65)
            contributions=exp.values[0,:,2];base=float(exp.base_values[0,2]);method='Permutation SHAP · 5 permutation cycles · 8 training references'
        elif selected=='tabpfn':
            estimator=load_tabpfn()
            probs=estimator.predict_proba(x)[0]
            exp=shap.Explainer(estimator.predict_proba,bundle['background'][:4],algorithm='permutation',seed=42)(x,max_evals=13)
            contributions=exp.values[0,:,2];base=float(exp.base_values[0,2]);method='Approximate permutation SHAP · 1 cycle · 4 training references'
        else:
            estimator=bundle['estimator'];probs=estimator.predict_proba(x)[0]
            explainer=shap.TreeExplainer(estimator)
            contributions=explainer.shap_values(x)[0,:,2];base=float(explainer.expected_value[2]);method='TreeSHAP · high mapped-susceptibility output'
    return {'status':'available','model':selected,'class_index':int(np.argmax(probs)),
            'class_names':['Low','Medium','High'],'class_scores':probs.tolist(),
            'explanation':{'method':method,'base_value':base,'output_value':float(probs[2]),
                'contributions':[{'feature':name,'value':float(x[0,i]),'contribution':float(contributions[i])} for i,name in enumerate(FEATURES)],
                'meaning':'Contributions explain this model’s high-class score, not causal effects or event probability.'},
            'limitation':'Pilot reproduces historical mapped classes. Class-balanced sampling; scores are not calibrated landslide probabilities.'}


@lru_cache(maxsize=1)
def load_baseline():
    import joblib
    return joblib.load(ROOT/'models/baseline.joblib')


@lru_cache(maxsize=1)
def load_tabpfn():
    from tabpfn.model_loading import load_fitted_tabpfn_model
    file=ROOT/'models/tabpfn.tabpfn_fit'
    if not file.exists():raise FileNotFoundError('TabPFN benchmark has not finished')
    return load_fitted_tabpfn_model(file,device='cpu')


@app.post('/api/analyze')
def analyze(location:Location):
    geo=geography()
    point=gpd.GeoSeries([Point(location.lon,location.lat)],crs=4326).to_crs(32643).iloc[0]
    if not geo['state'].geometry.iloc[0].covers(point):
        raise HTTPException(422,'Choose a location inside Kerala')
    area=point.buffer(location.radius_m)
    district=intersecting(geo['districts'],point)
    hits=intersecting(geo['hazards'],area)
    evidence=[]
    for label,group in hits.groupby('source_label'):
        overlap=group.geometry.union_all().intersection(area).area/area.area
        evidence.append({'label':label,'area_percent':round(overlap*100,1),'source':'KSDMA / NCESS historical maps','vintage':'2010 source attribution','point_intersection':bool(group.geometry.intersects(point).any())})
    nearby=[]
    for kind in ['hospital','pharmacy','school','grocery','bank','fire_station']:
        facilities=geo['amenities'][geo['amenities'].kind==kind]
        if facilities.empty:continue
        indices,distance=facilities.sindex.nearest(point,return_distance=True,return_all=False)
        item=facilities.iloc[int(indices[1,0])]
        nearby.append({'kind':kind,'name':item['name'],'distance_m':round(float(distance[0])),
            'source':'OpenStreetMap point amenities','distance_type':'Straight-line; not travel distance'})
    road_indices,road_distance=geo['roads'].sindex.nearest(point,return_distance=True,return_all=False)
    road=geo['roads'].iloc[int(road_indices[1,0])]
    terrain={};errors=[]
    try:terrain=measurements(round(location.lon,6),round(location.lat,6))
    except Exception as exc:errors.append({'source':'Earth Engine','type':type(exc).__name__,'message':'Measurements unavailable; do not infer safety from missing data'})
    try:estimate=prediction(terrain,location.model)
    except Exception as exc:estimate={'status':'unavailable','reason':f'Model inference unavailable ({type(exc).__name__})'}
    google_places=[]
    if os.environ.get('GOOGLE_PLACES_API_KEY'):
        try:google_places=nearby_places(location.lon,location.lat,max(3000,location.radius_m*4))
        except Exception as exc:errors.append({'source':'Google Places','type':type(exc).__name__,'message':'Live Google Maps places are temporarily unavailable; OpenStreetMap results remain visible'})
    flags=[e['label'] for e in evidence if e['label'] in {'High Hazard Zone','Flood plain','Waterbody'}]
    if flags:
        outcome='High concern';reason='The selected area intersects a historical mapped hazard. Examine the overlap and obtain a site assessment.'
    elif estimate.get('status')=='available' and estimate['class_index']==2:
        outcome='Further investigation';reason='The pilot model estimates high mapped landslide susceptibility, despite no high-hazard overlay intersection.'
    else:
        outcome='Evidence incomplete';reason='Available layers cannot establish that a house can safely or legally be built here.'
    outline=gpd.GeoSeries([area],crs=32643).to_crs(4326).iloc[0]
    return {'location':location.model_dump(),'district':district.iloc[0]['name'] if len(district) else 'Kerala boundary area',
            'outcome':outcome,'reason':reason,'area':mapping(outline),'hazards':evidence,
            'terrain':[{'feature':name,'value':terrain.get(name),**CATALOG[name]} for name in FEATURES],
            'nearby':nearby,'google_places':google_places,'road':{'distance_m':round(float(road_distance[0])),'kind':road.kind,'mapped_access':road.access,'caveat':'Mapped road proximity does not prove legal or emergency access'},
            'prediction':estimate,'errors':errors,
            'unknowns':['Soil bearing capacity and foundation design','Title, zoning, CRZ and wetland compliance','Drinking-water quality and seasonal supply','Electricity, sewage, broadband and waste-service connections','Crime, noise and site-specific air quality','Land price and construction cost'],
            'next_steps':['Have a geotechnical professional inspect soil and slope stability','Verify plot records and applicable restrictions with the local authority','Check monsoon drainage and physical/legal access on site'],
            'scope':'150m default neighbourhood screening; not a cadastral survey or construction clearance'}


if (ROOT/'web/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
