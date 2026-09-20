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
from shapely.geometry import Point, mapping, shape
from kerala_land_lab.earth import load_env, initialize, statewide_point_features, statewide_points_features, STATEWIDE_FEATURES, STATEWIDE_CATALOG
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


class AreaSelection(BaseModel):
    geometry:dict
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


def statewide_values_many(coordinates, points):
    global earth_ready
    with earth_lock:
        if not earth_ready:initialize();earth_ready=True
        rows=statewide_points_features(coordinates)
    point_frame=gpd.GeoDataFrame({'point_id':[f'area-{i}' for i in range(len(coordinates))]},geometry=[Point(lon,lat) for lon,lat in coordinates],crs=4326)
    point_frame=attach_gsi_landslide(point_frame,ROOT/'data')
    point_frame=attach_flood_levels(point_frame,ROOT/'data')
    geo=geography()
    for values,(_,row),point in zip(rows,point_frame.iterrows(),points):
        values.update({f'flood_level_{period}yr_m':float(row[f'flood_level_{period}yr_m']) for period in (10,25,50,100,200,500)})
        values['gsi_landslide_susceptibility']=row.gsi_landslide_susceptibility
        values['gsi_landslide_code']={'Not mapped':0,'Low':1,'Moderate':2,'High':3}[row.gsi_landslide_susceptibility]
        values['dist_nearest_road']=nearest_distance(geo['roads'],point)
        values['dist_nearest_highway']=nearest_distance(geo['roads'][geo['roads'].major.astype(bool)],point)
        for kind in ['hospital','school','quarry','bus_stop','railway_station','pharmacy','shop','bank','park','waste_facility','industrial']:
            values[f'dist_nearest_{kind}']=nearest_distance(geo['facilities'][geo['facilities'].kind==kind],point)
        values['dist_nearest_power_line']=nearest_distance(geo['power_lines'],point)
    return rows


SCORE_ANCHORS=np.array([0.08,0.34,0.64,0.90],dtype=np.float32)
FEATURE_GROUPS={
    'annual_rainfall':'Climate','mean_humidity':'Climate','mean_temperature':'Climate','mean_wind_speed':'Climate',
    'aspect':'Terrain','elevation':'Terrain','slope':'Terrain','terrain_ruggedness_index':'Terrain',
    'clay_content':'Soil','organic_carbon':'Soil','sand_content':'Soil','soil_ph':'Soil','water_content':'Soil',
    'distance_to_water':'Water & flood','flood_occurrence':'Water & flood',
    'flood_level_10yr_m':'Water & flood','flood_level_25yr_m':'Water & flood','flood_level_50yr_m':'Water & flood','flood_level_100yr_m':'Water & flood','flood_level_200yr_m':'Water & flood','flood_level_500yr_m':'Water & flood',
    'land_cover_class':'Land cover','ndvi':'Land cover','gsi_landslide_code':'Natural hazards',
    'dist_nearest_road':'Access','dist_nearest_highway':'Access','dist_nearest_bus_stop':'Access','dist_nearest_railway_station':'Access',
    'dist_nearest_hospital':'Amenities','dist_nearest_school':'Amenities','dist_nearest_pharmacy':'Amenities','dist_nearest_shop':'Amenities','dist_nearest_bank':'Amenities','dist_nearest_park':'Amenities',
    'dist_nearest_quarry':'Environmental exposure','dist_nearest_power_line':'Utilities','dist_nearest_waste_facility':'Environmental exposure','dist_nearest_industrial':'Environmental exposure',
}


def prediction(values,selected):
    import joblib
    import shap
    file=ROOT/'models/statewide/baseline.joblib'
    if not file.exists():return {'status':'unavailable','reason':'Training has not finished'}
    bundle=load_statewide_baseline()
    value_rows=values if isinstance(values,list) else [values]
    raw=np.array([[row.get(name,np.nan) for name in bundle['features']] for row in value_rows],dtype=np.float32)
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
            all_probs=predict(x); method='Permutation SHAP · statewide suitability score · 8 representative training medoids'
            predict_proba=predict
        elif selected=='tabpfn':
            estimator=load_statewide_tabpfn()
            all_probs=estimator.predict_proba(x); predict_proba=estimator.predict_proba
            method='Permutation SHAP · statewide suitability score · 8 representative training medoids'
        else:
            estimator=bundle['estimator'];all_probs=estimator.predict_proba(x);predict_proba=estimator.predict_proba
            method='Permutation SHAP · statewide suitability score · 8 representative training medoids'
        sample_scores=all_probs@SCORE_ANCHORS
        median=float(np.median(sample_scores));representative=int(np.argmin(np.abs(sample_scores-median)))
        probs=all_probs[representative]
        def predict_score(a):return predict_proba(a)@SCORE_ANCHORS
        references=representative_background()
        exp=shap.Explainer(predict_score,references,algorithm='permutation',seed=42)(x[representative:representative+1],max_evals=2*len(bundle['features'])+1)
        contributions=np.asarray(exp.values[0])*100;base=float(np.asarray(exp.base_values).reshape(-1)[0]*100)
    items=[];groups={}
    for i,name in enumerate(bundle['features']):
        contribution=float(contributions[i]);group=FEATURE_GROUPS.get(name,'Other')
        groups[group]=groups.get(group,0)+contribution
        items.append({'feature':name,'group':group,'value':None if np.isnan(raw[representative,i]) else float(raw[representative,i]),'contribution':contribution})
    score=float(sample_scores[representative]*100)
    return {'status':'available','model':selected,'class_index':int(np.argmax(probs)),
            'class_names':['Screen out','Low','Moderate','Higher'],'class_scores':probs.tolist(),
            'suitability_percent':round(score,1),
            'spatial_summary':{'samples':len(value_rows),'minimum_percent':round(float(sample_scores.min()*100),1),'maximum_percent':round(float(sample_scores.max()*100),1),'median_percent':round(float(np.median(sample_scores)*100),1)},
            'explanation':{'method':method,'base_value':round(base,2),'output_value':round(score,2),
                'contributions':items,'groups':[{'group':key,'contribution':round(value,2)} for key,value in sorted(groups.items(),key=lambda item:abs(item[1]),reverse=True)],
                'meaning':'SHAP values are percentage-point effects on the displayed suitability score. Positive values raise the score; negative values lower it. Effects describe this model, not physical causation.'},
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


@lru_cache(maxsize=1)
def representative_background():
    """Eight geographically pooled, feature-space medoids for SHAP masking."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    background=statewide_background();scaled=StandardScaler().fit_transform(background)
    clusters=KMeans(n_clusters=8,random_state=42,n_init=10).fit(scaled)
    indices=[]
    for center in clusters.cluster_centers_:
        distances=np.square(scaled-center).sum(axis=1);indices.append(int(np.argmin(distances)))
    return background[indices]


def score_outcome(estimate):
    if estimate.get('status')!='available':
        return 'Analysis unavailable','The model could not complete this assessment. Try again or choose another model.'
    score=estimate['suitability_percent']
    if score<25:return 'Very low suitability','The public-data model found several strong constraints at this location.'
    if score<50:return 'Low suitability','Mapped conditions contain material constraints that need specialist review.'
    if score<70:return 'Moderate suitability','The model found a mixed profile with both supportive and limiting conditions.'
    return 'Higher suitability','The mapped public-data profile is comparatively favourable within this experimental model.'


def sample_polygon(polygon,max_points=9):
    points=[polygon.representative_point()]
    minx,miny,maxx,maxy=polygon.bounds
    for y in np.linspace(miny,maxy,5)[1:-1]:
        for x in np.linspace(minx,maxx,5)[1:-1]:
            candidate=Point(float(x),float(y))
            if polygon.covers(candidate) and all(candidate.distance(existing)>.5 for existing in points):points.append(candidate)
    return points[:max_points]


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
    outcome,reason=score_outcome(estimate)
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


@app.post('/api/analyze-area')
def analyze_area(selection:AreaSelection):
    try:polygon_wgs=shape(selection.geometry)
    except Exception as exc:raise HTTPException(422,'Draw a valid polygon') from exc
    if polygon_wgs.geom_type!='Polygon' or not polygon_wgs.is_valid or polygon_wgs.area==0:raise HTTPException(422,'Draw a valid polygon')
    polygon=gpd.GeoSeries([polygon_wgs],crs=4326).to_crs(32643).iloc[0]
    if polygon.area<25:raise HTTPException(422,'Draw an area larger than 25 m²')
    if polygon.area>5_000_000:raise HTTPException(422,'Keep the selected area below 5 km²')
    geo=geography()
    if not geo['state'].geometry.iloc[0].covers(polygon):raise HTTPException(422,'Keep the polygon inside Kerala')
    points=sample_polygon(polygon)
    point_series=gpd.GeoSeries(points,crs=32643).to_crs(4326)
    coordinates=[(float(item.x),float(item.y)) for item in point_series]
    errors=[];rows=[]
    try:rows=statewide_values_many(coordinates,points)
    except Exception as exc:errors.append({'source':'Earth Engine','type':type(exc).__name__,'message':'Measurements unavailable; try again shortly'})
    try:estimate=prediction(rows,selection.model) if rows else {'status':'unavailable','reason':'Measurements unavailable'}
    except Exception as exc:estimate={'status':'unavailable','reason':f'Model inference unavailable ({type(exc).__name__})'}
    outcome,reason=score_outcome(estimate)
    representative=rows[0] if rows else {}
    centroid=polygon.representative_point();districts=intersecting(geo['districts'],polygon)
    nearby=[]
    for kind in ['hospital','pharmacy','school','grocery','bank','fire_station']:
        facilities=geo['amenities'][geo['amenities'].kind==kind]
        if facilities.empty:continue
        indices,distance=facilities.sindex.nearest(centroid,return_distance=True,return_all=False);item=facilities.iloc[int(indices[1,0])]
        nearby.append({'kind':kind,'name':item['name'],'distance_m':round(float(distance[0])),'source':'OpenStreetMap','distance_type':'Straight-line from area centre'})
    road_indices,road_distance=geo['roads'].sindex.nearest(centroid,return_distance=True,return_all=False);road=geo['roads'].iloc[int(road_indices[1,0])]
    centroid_wgs=gpd.GeoSeries([centroid],crs=32643).to_crs(4326).iloc[0]
    return {'location':{'lat':centroid_wgs.y,'lon':centroid_wgs.x,'area_m2':round(polygon.area),'selection_type':'polygon','sample_count':len(points),'model':selection.model},
            'district':', '.join(sorted(districts.name.unique())) if len(districts) else 'Kerala boundary area','outcome':outcome,'reason':reason,'area':mapping(polygon_wgs),'hazards':[],
            'terrain':[{'feature':name,'value':representative.get(name),**STATEWIDE_CATALOG[name]} for name in STATEWIDE_FEATURES],
            'nearby':nearby,'google_places':[],'road':{'distance_m':round(float(road_distance[0])),'kind':road.kind,'mapped_access':road.access,'caveat':'Mapped road proximity does not prove legal access'},
            'prediction':estimate,'errors':errors,'scope':f'{round(polygon.area):,} m² polygon sampled at {len(points)} locations; not a cadastral survey or construction clearance'}


if (ROOT/'web/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
