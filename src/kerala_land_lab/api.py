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
from kerala_land_lab.earth import load_env, initialize, statewide_point_features, STATEWIDE_FEATURES, STATEWIDE_CATALOG
from kerala_land_lab.current_hazards import attach_flood_levels, attach_gsi_landslide
from kerala_land_lab.places import nearby_places
from kerala_land_lab.weak_labels import LABEL_NAMES

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
            'facilities':gpd.read_file(DATA/'facilities.gpkg').to_crs(32643),
            'power_lines':gpd.read_file(DATA/'power_lines.gpkg').to_crs(32643),
            'roads':gpd.read_file(DATA/'roads.gpkg').to_crs(32643)}


class Location(BaseModel):
    lat:float=Field(ge=8,le=13)
    lon:float=Field(ge=74,le=78)
    radius_m:int=Field(default=150,ge=50,le=500)
    model:str=Field(default='tabpfn',pattern='^(extra_trees|feature_transformer|tabpfn)$')


@app.get('/api/config')
def config():
    evaluation=ROOT/'models/statewide/evaluation.json'
    return {'mapbox_token':os.environ.get('MAPBOX_PUBLIC_TOKEN',''),
            'evaluation':json.loads(evaluation.read_text()) if evaluation.exists() else None,
            'earth_project_configured':bool(os.environ.get('PROJECT_ID')),
            'google_places_configured':bool(os.environ.get('GOOGLE_PLACES_API_KEY')),
            'research_status':'Statewide public-data screening model; expert construction suitability not validated'}


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
        return statewide_point_features(lon,lat)


def nearest_distance(frame, point):
    if frame.empty:return float('nan')
    indices,distance=frame.sindex.nearest(point,return_distance=True,return_all=False)
    return float(distance[0])


def statewide_values(lon,lat,point):
    values=measurements(round(lon,6),round(lat,6))
    point_frame=gpd.GeoDataFrame({'point_id':['request']},geometry=[Point(lon,lat)],crs=4326)
    point_frame=attach_gsi_landslide(point_frame,ROOT/'data')
    point_frame=attach_flood_levels(point_frame,ROOT/'data')
    row=point_frame.iloc[0]
    values.update({f'flood_level_{period}yr_m':float(row[f'flood_level_{period}yr_m']) for period in (10,25,50,100,200,500)})
    values['gsi_landslide_susceptibility']=row.gsi_landslide_susceptibility
    values['gsi_landslide_code']={'Not mapped':0,'Low':1,'Moderate':2,'High':3}[row.gsi_landslide_susceptibility]
    geo=geography()
    values['dist_nearest_road']=nearest_distance(geo['roads'],point)
    values['dist_nearest_highway']=nearest_distance(geo['roads'][geo['roads'].major.astype(bool)],point)
    for kind in ['hospital','school','quarry','bus_stop','railway_station','pharmacy','shop','bank','park','waste_facility','industrial']:
        values[f'dist_nearest_{kind}']=nearest_distance(geo['facilities'][geo['facilities'].kind==kind],point)
    values['dist_nearest_power_line']=nearest_distance(geo['power_lines'],point)
    return values


def prediction(values,selected):
    import joblib
    import shap
    file=ROOT/'models/statewide/baseline.joblib'
    if not file.exists():return {'status':'unavailable','reason':'Training has not finished'}
    bundle=load_statewide_baseline()
    raw=np.array([[values.get(name,np.nan) for name in bundle['features']]],dtype=np.float32)
    x=bundle['imputer'].transform(raw).astype(np.float32)
    background=statewide_background()
    with model_lock:
        if selected=='feature_transformer':
            import torch
            from kerala_land_lab.model import FeatureTransformer
            preprocessing=joblib.load(ROOT/'models/statewide/transformer_preprocessing.joblib');scaler=preprocessing['scaler']
            network=FeatureTransformer(len(bundle['features']),n_classes=4);network.load_state_dict(torch.load(ROOT/'models/statewide/feature_transformer.pt',map_location='cpu',weights_only=True));network.eval()
            def predict(a):
                with torch.no_grad():return torch.softmax(network(torch.tensor(scaler.transform(a),dtype=torch.float32)),dim=1).numpy()
            probs=predict(x)[0]
            target=int(np.argmax(probs));exp=shap.Explainer(predict,background[:8],algorithm='permutation',seed=42)(x,max_evals=2*len(bundle['features'])+1)
            contributions=exp.values[0,:,target];base=float(exp.base_values[0,target]);method='Permutation SHAP · 8 training references'
        elif selected=='tabpfn':
            estimator=load_statewide_tabpfn()
            probs=estimator.predict_proba(x)[0]
            target=int(np.argmax(probs));exp=shap.Explainer(estimator.predict_proba,background[:4],algorithm='permutation',seed=42)(x,max_evals=2*len(bundle['features'])+1)
            contributions=exp.values[0,:,target];base=float(exp.base_values[0,target]);method='Permutation SHAP · 4 training references'
        else:
            estimator=bundle['estimator'];probs=estimator.predict_proba(x)[0]
            target=int(np.argmax(probs));explainer=shap.TreeExplainer(estimator)
            shap_values=explainer.shap_values(x);contributions=shap_values[0,:,target] if np.asarray(shap_values).ndim==3 else shap_values[target][0]
            base=np.asarray(explainer.expected_value).reshape(-1)[target];method='TreeSHAP · predicted screening-class output'
    return {'status':'available','model':selected,'class_index':int(np.argmax(probs)),
            'class_names':[LABEL_NAMES[i].replace('_public_data','').replace('_',' ').title() for i in range(4)],'class_scores':probs.tolist(),
            'explanation':{'method':method,'base_value':float(base),'output_value':float(probs[target]),
                'contributions':[{'feature':name,'value':None if np.isnan(raw[0,i]) else float(raw[0,i]),'contribution':float(contributions[i])} for i,name in enumerate(bundle['features'])],
                'meaning':'Contributions explain the selected screening class. They are associations with a weak-label model, not causal effects or safety probabilities.'},
            'limitation':'Model reproduces transparent public-data weak labels. It is not expert ground truth, a permit decision, or proof that construction is safe.'}


@lru_cache(maxsize=1)
def load_statewide_baseline():
    import joblib
    return joblib.load(ROOT/'models/statewide/baseline.joblib')


@lru_cache(maxsize=1)
def load_statewide_tabpfn():
    from tabpfn.model_loading import load_fitted_tabpfn_model
    file=ROOT/'models/statewide/tabpfn.tabpfn_fit'
    if not file.exists():raise FileNotFoundError('TabPFN benchmark has not finished')
    return load_fitted_tabpfn_model(file,device='cpu')


@lru_cache(maxsize=1)
def statewide_background():
    import pandas as pd
    bundle=load_statewide_baseline();frame=pd.read_csv(DATA/'kerala_statewide_features.csv')
    frame['gsi_landslide_code']=frame.gsi_landslide_susceptibility.map({'Not mapped':0,'Low':1,'Moderate':2,'High':3})
    frame=frame[frame.district.isin(bundle['training_districts'])]
    return bundle['imputer'].transform(frame[bundle['features']].to_numpy(dtype=np.float32)).astype(np.float32)


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
    try:terrain=statewide_values(location.lon,location.lat,point)
    except Exception as exc:errors.append({'source':'Earth Engine','type':type(exc).__name__,'message':'Measurements unavailable; do not infer safety from missing data'})
    try:estimate=prediction(terrain,location.model)
    except Exception as exc:estimate={'status':'unavailable','reason':f'Model inference unavailable ({type(exc).__name__})'}
    google_places=[]
    if os.environ.get('GOOGLE_PLACES_API_KEY'):
        try:google_places=nearby_places(location.lon,location.lat,max(3000,location.radius_m*4))
        except Exception as exc:errors.append({'source':'Google Places','type':type(exc).__name__,'message':'Live Google Maps places are temporarily unavailable; OpenStreetMap results remain visible'})
    current_flags=(terrain.get('gsi_landslide_susceptibility')=='High' or (terrain.get('flood_level_10yr_m') or 0)>0)
    flags=[e['label'] for e in evidence if e['label'] in {'High Hazard Zone','Flood plain','Waterbody'}]
    if current_flags or flags:
        outcome='High concern';reason='The selected area intersects a historical mapped hazard. Examine the overlap and obtain a site assessment.'
    elif estimate.get('status')=='available' and estimate['class_index']<=1:
        outcome='Further investigation';reason='The statewide screening model places this location in a high-concern public-data class.'
    elif estimate.get('status')=='available' and estimate['class_index']==2:
        outcome='Review recommended';reason='The statewide screening model places this location in the moderate public-data suitability class.'
    else:
        outcome='Evidence incomplete';reason='Available layers cannot establish that a house can safely or legally be built here.'
    outline=gpd.GeoSeries([area],crs=32643).to_crs(4326).iloc[0]
    return {'location':location.model_dump(),'district':district.iloc[0]['name'] if len(district) else 'Kerala boundary area',
            'outcome':outcome,'reason':reason,'area':mapping(outline),'hazards':evidence,
            'terrain':[{'feature':name,'value':terrain.get(name),**STATEWIDE_CATALOG[name]} for name in STATEWIDE_FEATURES],
            'current_hazards':{'gsi_landslide_susceptibility':terrain.get('gsi_landslide_susceptibility'),
                'flood_levels_m':{str(period):terrain.get(f'flood_level_{period}yr_m') for period in (10,25,50,100,200,500)},
                'source':'GSI 2022 and KSDMA/UNEP historical flood-return rasters'},
            'nearby':nearby,'google_places':google_places,'road':{'distance_m':round(float(road_distance[0])),'kind':road.kind,'mapped_access':road.access,'caveat':'Mapped road proximity does not prove legal or emergency access'},
            'prediction':estimate,'errors':errors,
            'unknowns':['Soil bearing capacity and foundation design','Title, zoning, CRZ and wetland compliance','Drinking-water quality and seasonal supply','Electricity, sewage, broadband and waste-service connections','Crime, noise and site-specific air quality','Land price and construction cost'],
            'next_steps':['Have a geotechnical professional inspect soil and slope stability','Verify plot records and applicable restrictions with the local authority','Check monsoon drainage and physical/legal access on site'],
            'scope':'150m default neighbourhood screening; not a cadastral survey or construction clearance'}


if (ROOT/'web/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
