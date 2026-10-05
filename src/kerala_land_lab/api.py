"""Local research API. Bind to localhost; no production security claims."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from functools import lru_cache
from contextlib import asynccontextmanager
from threading import Lock, Thread
import tempfile
from typing import Literal
import geopandas as gpd
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping, shape
from kerala_land_lab.earth import load_env, initialize, statewide_point_features, statewide_points_features, search_points_features, STATEWIDE_FEATURES, STATEWIDE_CATALOG
from kerala_land_lab.current_hazards import attach_flood_levels, attach_gsi_landslide
from kerala_land_lab.weak_labels import LABEL_NAMES
from kerala_land_lab.fusion import FusionConfig, combine_probabilities
from kerala_land_lab.search import (
    NON_BUILDABLE_COVER_CLASSES,
    OPEN_LAND_CLASSES,
    candidate_grid,
    eligible_candidate_mask,
    rank_candidates,
)
from kerala_land_lab.semantic import interpret_request, semantic_status

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/processed'
load_env()
earth_lock=Lock();model_lock=Lock();satellite_lock=Lock();earth_ready=False


@asynccontextmanager
async def lifespan(_:FastAPI):
    Thread(target=_warm_models,daemon=True).start()
    yield


app=FastAPI(title='Nilam · Kerala Land Lab',version='0.3.0',lifespan=lifespan)


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
    detail:Literal['preview','full','explain']='full'


class AreaSelection(BaseModel):
    geometry:dict
    detail:Literal['preview','full','explain']='full'


class SearchAreaInput(BaseModel):
    district:str|None=None
    center_lat:float|None=Field(default=None,ge=8,le=13)
    center_lon:float|None=Field(default=None,ge=74,le=78)
    radius_km:float|None=Field(default=None,gt=0,le=250)
    geometry:dict|None=None


class CandidateSearch(BaseModel):
    area:SearchAreaInput
    requirements:dict=Field(default_factory=dict)
    query:str=''
    limit:int=Field(default=20,ge=1,le=40)


class PreferenceText(BaseModel):
    text:str=Field(min_length=1,max_length=2000)


@app.get('/api/config')
def config():
    evaluation=ROOT/'models/statewide/evaluation.json'
    multimodal_evaluation=ROOT/'models/multimodal_v2/evaluation.json'
    fusion_evaluation=ROOT/'models/terramind_tabpfn/evaluation.json'
    google_key=os.environ.get('GOOGLE_MAPS_API_KEY') or os.environ.get('GOOGLE_PLACES_API_KEY','')
    return {'google_maps_api_key':google_key,
            'evaluation':json.loads(evaluation.read_text()) if evaluation.exists() else None,
            'multimodal_evaluation':json.loads(multimodal_evaluation.read_text()) if multimodal_evaluation.exists() else None,
            'fusion_evaluation':json.loads(fusion_evaluation.read_text()) if fusion_evaluation.exists() else None,
            'fusion_available':(ROOT/'models/multimodal_v2/terramind_tabular_fusion.pt').exists() and (ROOT/'models/statewide/tabpfn.tabpfn_fit').exists(),
            'product_model':'TerraMind + TabPFN adaptive fusion',
            'earth_project_configured':bool(os.environ.get('PROJECT_ID')),
            'google_maps_configured':bool(google_key),
            'semantic':semantic_status(),
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
    cache_dir=ROOT/'data/cache/earth'
    cache_dir.mkdir(parents=True,exist_ok=True)
    cache_file=cache_dir/f'{float(lat):.4f}_{float(lon):.4f}.json'
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    with earth_lock:
        if not earth_ready:initialize();earth_ready=True
        values=statewide_point_features(lon,lat)
    temporary=cache_file.with_suffix('.tmp')
    temporary.write_text(json.dumps(values))
    temporary.replace(cache_file)
    return values


def nearest_distance(frame, point):
    if frame.empty:return float('nan')
    indices,distance=frame.sindex.nearest(point,return_distance=True,return_all=False)
    return float(distance[0])


def nearest_distances(frame, points):
    """Vectorised nearest-feature distances in the projected Kerala CRS."""
    result=np.full(len(points),np.nan,dtype=float)
    if frame.empty or not points:return result
    indices,distances=frame.sindex.nearest(gpd.GeoSeries(points,crs=32643),return_distance=True,return_all=False)
    for source,distance in zip(indices[0],distances):
        if np.isnan(result[source]) or distance<result[source]:result[source]=float(distance)
    return result


def statewide_values(lon,lat,point):
    values=measurements(round(lon,4),round(lat,4))
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


@lru_cache(maxsize=1)
def building_tree():
    path=DATA/'osm_building_centres.npz'
    if not path.exists():return None
    from scipy.spatial import cKDTree
    values=np.load(path)
    return cKDTree(np.column_stack([values['x'],values['y']]))


@lru_cache(maxsize=1)
def candidate_spatial_index():
    from scipy.spatial import cKDTree
    frame=candidate_index()
    return cKDTree(np.column_stack([frame.lng.to_numpy(dtype=float),frame.lat.to_numpy(dtype=float)]))


def interpolated_statewide_rows(coordinates,k=6):
    """IDW interpolation for slow-changing soil and climate training fields."""
    frame=candidate_index();tree=candidate_spatial_index()
    query=np.asarray(coordinates,dtype=float)
    distances,indices=tree.query(query,k=min(k,len(frame)))
    if distances.ndim==1:distances=distances[:,None];indices=indices[:,None]
    weights=1/np.maximum(distances,1e-6)**2
    rows=[]
    for point_indices,point_weights in zip(indices,weights):
        neighbours=frame.iloc[np.asarray(point_indices)]
        row={}
        for name in STATEWIDE_FEATURES:
            values=__import__('pandas').to_numeric(neighbours[name],errors='coerce').to_numpy(dtype=float)
            valid=np.isfinite(values)
            row[name]=float(np.average(values[valid],weights=point_weights[valid])) if valid.any() else None
        rows.append(row)
    return rows


def enrich_search_rows(rows,coordinates,projected_points):
    point_frame=gpd.GeoDataFrame(
        {'point_id':[f'search-{i}' for i in range(len(coordinates))]},
        geometry=[Point(lon,lat) for lon,lat in coordinates],crs=4326,
    )
    point_frame=attach_gsi_landslide(point_frame,ROOT/'data')
    point_frame=attach_flood_levels(point_frame,ROOT/'data')
    districts=gpd.sjoin(point_frame,geography()['districts'][['name','geometry']].to_crs(4326),predicate='within',how='left')
    district_names=districts.groupby('point_id').name.first().to_dict()
    geo=geography();tree=building_tree()
    building_distances=np.full(len(coordinates),np.nan)
    if tree is not None:
        xy=np.array([[point.x,point.y] for point in projected_points],dtype=float)
        building_distances=tree.query(xy,k=1)[0]
    distance_columns={
        'dist_nearest_road':nearest_distances(geo['roads'],projected_points),
        'dist_nearest_highway':nearest_distances(geo['roads'][geo['roads'].major.astype(bool)],projected_points),
        'dist_nearest_power_line':nearest_distances(geo['power_lines'],projected_points),
    }
    for kind in ['hospital','school','quarry','bus_stop','railway_station','pharmacy','shop','bank','park','waste_facility','industrial']:
        distance_columns[f'dist_nearest_{kind}']=nearest_distances(geo['facilities'][geo['facilities'].kind==kind],projected_points)
    for index,(values,(_,hazard)) in enumerate(zip(rows,point_frame.iterrows())):
        values.update({f'flood_level_{period}yr_m':float(hazard[f'flood_level_{period}yr_m']) for period in (10,25,50,100,200,500)})
        values['gsi_landslide_susceptibility']=hazard.gsi_landslide_susceptibility
        values['gsi_landslide_code']={'Not mapped':0,'Low':1,'Moderate':2,'High':3}[hazard.gsi_landslide_susceptibility]
        values['district']=district_names.get(hazard.point_id) or 'Kerala'
        for column,distances in distance_columns.items():values[column]=float(distances[index])
        values['building_distance_m']=float(building_distances[index])
    return rows


@lru_cache(maxsize=24)
def live_search_frame(center_lat,center_lon,radius_km):
    grid=candidate_grid(center_lat,center_lon,radius_km)
    points=gpd.GeoDataFrame(grid.copy(),geometry=gpd.points_from_xy(grid.lng,grid.lat),crs=4326)
    projected=points.to_crs(32643)
    state=geography()['state'].geometry.iloc[0]
    keep=np.array([state.covers(point) for point in projected.geometry],dtype=bool)
    points=points.loc[keep].reset_index(drop=True);projected=projected.loc[keep].reset_index(drop=True)
    initial_grid_points=len(points)
    coordinates=list(zip(points.lng.astype(float),points.lat.astype(float)))
    global earth_ready
    with earth_lock:
        if not earth_ready:initialize();earth_ready=True
        fresh_rows=search_points_features(coordinates)

    # Screen the complete radius with satellite and terrain evidence before
    # spending time on the tabular model and detailed proximity calculations.
    # The previous building-first sample could skip a small visible clearing.
    fresh=__import__('pandas').DataFrame(fresh_rows)
    tree=building_tree()
    building_distances=np.full(len(points),np.nan)
    if tree is not None and len(points):
        xy=np.column_stack([projected.geometry.x.to_numpy(),projected.geometry.y.to_numpy()])
        building_distances=tree.query(xy,k=1)[0]
    def numeric(name,default):
        values=fresh[name] if name in fresh else __import__('pandas').Series(default,index=fresh.index)
        return __import__('pandas').to_numeric(values,errors='coerce').fillna(default).to_numpy(dtype=float)
    cover=numeric('land_cover_class',-1)
    slope=numeric('slope',90);mean_slope=numeric('slope_mean_45m',90)
    robust_slope=numeric('slope_p90_45m',90);height_variation=numeric('elevation_stddev_45m',90)
    open_probability=numeric('open_probability_45m',0)
    built=numeric('built_probability',1);built_near=numeric('built_probability_45m',1)
    cover_open=np.isin(cover,list(OPEN_LAND_CLASSES))
    clear=(
        (slope<=8)&(mean_slope<=7)&(robust_slope<=10)&(height_variation<=5)&
        ~np.isin(cover,list(NON_BUILDABLE_COVER_CLASSES))&
        (open_probability>=.12)&(cover_open|(open_probability>=.18))&
        (built<=.35)&(built_near<=.30)
    )
    if tree is not None:clear &= building_distances>=30
    satellite_candidates=np.flatnonzero(clear)
    if len(satellite_candidates)>500:
        flat_score=(.4*np.clip(1-mean_slope/7,0,1)+.35*np.clip(1-robust_slope/10,0,1)+.25*np.clip(1-height_variation/5,0,1))
        open_score=.55*np.clip(open_probability/.45,0,1)+.25*(1-built_near)+.20*np.clip(building_distances/150,0,1)
        priority=.55*flat_score+.45*open_score
        satellite_candidates=satellite_candidates[np.argsort(priority[satellite_candidates])[::-1][:500]]
    points=points.iloc[satellite_candidates].reset_index(drop=True)
    projected=projected.iloc[satellite_candidates].reset_index(drop=True)
    fresh_rows=[fresh_rows[index] for index in satellite_candidates]
    coordinates=list(zip(points.lng.astype(float),points.lat.astype(float)))
    if not coordinates:
        frame=points.drop(columns='geometry').reset_index(drop=True)
        frame.attrs.update(initial_grid_points=initial_grid_points,earth_measured_points=initial_grid_points,satellite_candidate_points=0)
        return frame
    rows=interpolated_statewide_rows(coordinates)
    for row,fresh in zip(rows,fresh_rows):row.update(fresh)
    rows=enrich_search_rows(rows,coordinates,list(projected.geometry))
    frame=points.drop(columns='geometry').reset_index(drop=True)
    measured=__import__('pandas').DataFrame(rows)
    for column in measured.columns:frame[column]=measured[column]
    frame.attrs.update(initial_grid_points=initial_grid_points,earth_measured_points=initial_grid_points,satellite_candidate_points=len(satellite_candidates))
    return frame


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


def _tabular_arrays(value_rows):
    bundle=load_statewide_baseline()
    raw=np.array([[row.get(name,np.nan) for name in bundle['features']] for row in value_rows],dtype=np.float32)
    imputed=bundle['imputer'].transform(raw).astype(np.float32)
    return bundle,raw,imputed


def _tabpfn_probabilities(imputed):
    with model_lock:
        return load_statewide_tabpfn().predict_proba(imputed).astype(np.float32)


def prediction(values,coordinates=None,detail='full'):
    value_rows=values if isinstance(values,list) else [values]
    if not (ROOT/'models/statewide/tabpfn.tabpfn_fit').exists():
        return {'status':'unavailable','reason':'The trained TabPFN artifact is unavailable'}
    bundle,raw,imputed=_tabular_arrays(value_rows)
    tabpfn_probs=_tabpfn_probabilities(imputed)
    if detail=='preview':
        sample_scores=tabpfn_probs@SCORE_ANCHORS
        representative=int(np.argmin(np.abs(sample_scores-np.median(sample_scores))))
        score=float(sample_scores[representative]*100);probs=tabpfn_probs[representative]
        return {'status':'available','model':'terramind_tabpfn','analysis_stage':'mapped','class_index':int(np.argmax(probs)),
                'class_names':['Screen out','Low','Moderate','Higher'],'class_scores':probs.tolist(),'suitability_percent':round(score,1),
                'spatial_summary':{'samples':len(value_rows),'minimum_percent':round(float(sample_scores.min()*100),1),'maximum_percent':round(float(sample_scores.max()*100),1),'median_percent':round(float(np.median(sample_scores)*100),1)},
                'multimodal':{'version':'v3','architecture':'TerraMind + TabPFN adaptive late fusion','stage':'mapped','branch_scores':{'tabpfn':round(score,1),'fused':round(score,1)},'routing_weights':{'tabpfn':100.0,'terramind':0.0},
                    'meaning':'This fast preview uses mapped TabPFN evidence while the TerraMind satellite expert is loading.'},
                'explanation':{'status':'pending','contributions':[],'groups':[],'meaning':'Detailed SHAP attribution loads after the combined satellite result.'},
                'limitation':'Preview only. The final combined result follows after TerraMind satellite analysis.'}
    if not coordinates:
        return {'status':'unavailable','reason':'Satellite coordinates were not supplied'}
    return terramind_tabpfn_prediction(value_rows,coordinates,raw,imputed,tabpfn_probs,explain=detail=='explain')


@lru_cache(maxsize=1)
def load_multimodal_bundle():
    import joblib
    import torch
    from kerala_land_lab.model import FeatureTransformer
    from kerala_land_lab.multimodal import MultimodalFusionModel, build_terramind

    artifact=ROOT/'models/multimodal_v2/terramind_tabular_fusion.pt'
    if not artifact.exists():raise FileNotFoundError('Multimodal v2 training artifact is unavailable')
    saved=torch.load(artifact,map_location='cpu',weights_only=True)
    backbone,dimension=build_terramind(variant=saved.get('variant','base'),pretrained=False)
    expert=FeatureTransformer(len(saved['features']),dimension=32,n_classes=4)
    network=MultimodalFusionModel(backbone,len(saved['features']),dimension,tabular_expert=expert)
    network.load_state_dict(saved['state_dict'])
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu')
    network.to(device).eval()
    preprocessing=joblib.load(ROOT/'models/statewide/transformer_preprocessing.joblib')
    if preprocessing['features']!=saved['features']:raise RuntimeError('Multimodal feature order does not match preprocessing')
    return {'network':network,'device':device,'preprocessing':preprocessing,'features':saved['features']}


def live_satellite_chips(coordinates):
    global earth_ready
    from kerala_land_lab.satellite import sentinel2_chip
    with earth_lock:
        if not earth_ready:initialize();earth_ready=True
    with satellite_lock:
        return [sentinel2_chip(round(float(lon),4),round(float(lat),4)) for lon,lat in coordinates]


def _terramind_probabilities(coordinates,scaled):
    import torch
    from kerala_land_lab.multimodal import normalize_chip
    bundle=load_multimodal_bundle();network=bundle['network'];device=bundle['device']
    keys=[(round(float(lon),4),round(float(lat),4)) for lon,lat in coordinates]
    unique=[]
    for key in keys:
        if key not in unique:unique.append(key)
    cache_dir=ROOT/'data/cache/terramind';cache_dir.mkdir(parents=True,exist_ok=True)
    probabilities={};missing=[]
    for key in unique:
        path=cache_dir/f'{key[1]:.4f}_{key[0]:.4f}.json'
        if path.exists():probabilities[key]=np.asarray(json.loads(path.read_text())['probabilities'],dtype=np.float32)
        else:missing.append(key)
    if missing:
        chips=torch.stack([normalize_chip(chip) for chip in live_satellite_chips(missing)])
        indices=[keys.index(key) for key in missing]
        tabular=torch.tensor(scaled[indices],dtype=torch.float32,device=device)
        with model_lock,torch.inference_mode():
            result=network(chips.to(device),tabular)
            values=torch.softmax(result['vision'],dim=1).cpu().numpy()
        for key,value in zip(missing,values):
            probabilities[key]=value.astype(np.float32)
            path=cache_dir/f'{key[1]:.4f}_{key[0]:.4f}.json';temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'probabilities':value.tolist(),'model':'TerraMind Base vision head','seasons':['dry','monsoon']}));temporary.replace(path)
    return np.stack([probabilities[key] for key in keys])


def terramind_tabpfn_prediction(value_rows,coordinates,raw,imputed,tabpfn_probs,explain=False):
    if len(value_rows)!=len(coordinates):raise ValueError('Every feature row needs satellite coordinates')
    preprocessing=load_multimodal_bundle()['preprocessing'];features=load_multimodal_bundle()['features']
    scaled=preprocessing['scaler'].transform(imputed).astype(np.float32)
    vision_probs=_terramind_probabilities(coordinates,scaled)
    fusion_config=FusionConfig.load(ROOT/'models/terramind_tabpfn/fusion.json')
    fused_probs,vision_weights=combine_probabilities(tabpfn_probs,vision_probs,fusion_config)
    sample_scores=fused_probs@SCORE_ANCHORS
    representative=int(np.argmin(np.abs(sample_scores-np.median(sample_scores))))
    score=float(sample_scores[representative]*100);probs=fused_probs[representative]
    explanation={'status':'pending','contributions':[],'groups':[],'meaning':'Detailed SHAP attribution is loading.'}
    if explain:
        import shap
        fixed_vision=vision_probs[representative:representative+1]
        def predict_score(a):
            tabular=_tabpfn_probabilities(np.asarray(a,dtype=np.float32))
            vision=np.repeat(fixed_vision,len(tabular),axis=0)
            fused,_=combine_probabilities(tabular,vision,fusion_config)
            return fused@SCORE_ANCHORS
        references=representative_background()[::2]
        exp=shap.Explainer(predict_score,references,algorithm='permutation',seed=42)(imputed[representative:representative+1],max_evals=2*len(features)+1)
        contributions=np.asarray(exp.values[0])*100;base=float(np.asarray(exp.base_values).reshape(-1)[0]*100)
        items=[];groups={}
        for index,name in enumerate(features):
            contribution=float(contributions[index]);group=FEATURE_GROUPS.get(name,'Other');groups[group]=groups.get(group,0)+contribution
            items.append({'feature':name,'group':group,'value':None if np.isnan(raw[representative,index]) else float(raw[representative,index]),'contribution':contribution})
        explanation={'status':'ready','method':'Conditional permutation SHAP · TerraMind satellite evidence held fixed · TabPFN perturbed against 4 training medoids','base_value':round(base,2),'output_value':round(score,2),'contributions':items,
            'groups':[{'group':key,'contribution':round(value,2)} for key,value in sorted(groups.items(),key=lambda item:abs(item[1]),reverse=True)],
            'meaning':'SHAP values are percentage-point effects of mapped evidence on the combined score while TerraMind evidence is held fixed. Positive values raise the score; negative values lower it.'}
    tabular_score=tabpfn_probs@SCORE_ANCHORS;vision_score=vision_probs@SCORE_ANCHORS
    branch_scores={'terramind':round(float(np.median(vision_score)*100),1),'tabpfn':round(float(np.median(tabular_score)*100),1),'fused':round(score,1)}
    vision_weight=float(np.mean(vision_weights)*100)
    return {'status':'available','model':'terramind_tabpfn','analysis_stage':'explained' if explain else 'satellite','class_index':int(np.argmax(probs)),
            'class_names':['Screen out','Low','Moderate','Higher'],'class_scores':probs.tolist(),'suitability_percent':round(score,1),
            'spatial_summary':{'samples':len(value_rows),'minimum_percent':round(float(sample_scores.min()*100),1),'maximum_percent':round(float(sample_scores.max()*100),1),'median_percent':round(float(np.median(sample_scores)*100),1)},
            'multimodal':{'version':'v3','architecture':'TerraMind Base + TabPFN 3.5 adaptive late fusion','stage':'explained' if explain else 'satellite','satellite_source':'Sentinel-2 L2A · dry and monsoon composites','seasons':['Dry · Jan–Mar','Monsoon · Jun–Sep'],'spectral_bands':12,
                'satellite_contexts':len(set((round(float(lon),4),round(float(lat),4)) for lon,lat in coordinates)),
                'routing_weights':{'terramind':round(vision_weight,1),'tabpfn':round(100-vision_weight,1)},'branch_scores':branch_scores,
                'quality_gate_passed':fusion_config.quality_gate_passed,
                'meaning':'TerraMind reads seasonal satellite structure. TabPFN evaluates 38 mapped features. A validation-calibrated agreement gate combines their class probabilities.'},
            'explanation':explanation,
            'limitation':'The fusion predicts experimental weak labels. It is public-data screening, not expert ground truth, a permit decision, or proof that construction is safe.'}


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
        return 'Analysis unavailable','The combined model could not complete this assessment. Try the location again.'
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


@lru_cache(maxsize=1)
def candidate_index():
    import pandas as pd
    parquet=DATA/'kerala_search_index.parquet'
    csv=DATA/'kerala_search_index.csv'
    frame=pd.read_parquet(parquet) if parquet.exists() else pd.read_csv(csv if csv.exists() else DATA/'kerala_statewide_features.csv')
    frame['gsi_landslide_code']=frame.gsi_landslide_susceptibility.map({'Not mapped':0,'Low':1,'Moderate':2,'High':3})
    return frame


def indexed_values_near(coordinates):
    """Return nearest precomputed rows for an immediate, clearly marked preview."""
    frame=candidate_index()
    latitudes=frame.lat.to_numpy(dtype=float);longitudes=frame.lng.to_numpy(dtype=float)
    rows=[]
    for lon,lat in coordinates:
        distance=(latitudes-float(lat))**2+(longitudes-float(lon))**2
        rows.append(frame.iloc[int(np.argmin(distance))].to_dict())
    return rows


@app.post('/api/preferences/interpret')
def interpret_preferences(request:PreferenceText):
    return interpret_request(request.text)


@app.post('/api/search')
def search_candidates(request:CandidateSearch):
    interpreted=interpret_request(request.query) if request.query.strip() else {'requirements':{},'semantic':{'engine':'form'}}
    requirements={'prefer_open_land':True,'avoid_high_flood':True,'avoid_high_landslide':True,'max_slope':8,**interpreted.get('requirements',{}),**request.requirements}
    requirements['max_slope']=min(float(requirements.get('max_slope',8)),8)
    if request.area.center_lat is None or request.area.center_lon is None or request.area.radius_km is None:
        raise HTTPException(422,'Select a search centre and radius on the map')
    center_wgs=Point(request.area.center_lon,request.area.center_lat)
    center=gpd.GeoSeries([center_wgs],crs=4326).to_crs(32643).iloc[0]
    if not geography()['state'].geometry.iloc[0].covers(center):
        raise HTTPException(422,'Choose a search centre inside Kerala')
    try:selected=live_search_frame(request.area.center_lat,request.area.center_lon,request.area.radius_km)
    except Exception as exc:
        raise HTTPException(503,f'Live land screening could not finish ({type(exc).__name__}). Try this area again.') from exc
    if selected.empty:
        return {'candidates':[],'searched_points':selected.attrs.get('initial_grid_points',0),'measured_points':selected.attrs.get('earth_measured_points',0),'satellite_candidate_points':0,'eligible_points':0,'message':'No flat, open cells passed the satellite and terrain screen in this radius.','requirements':requirements,'semantic':interpreted.get('semantic',{})}
    _,_,imputed=_tabular_arrays(selected.to_dict('records'))
    probabilities=_tabpfn_probabilities(imputed)
    suitability=probabilities@SCORE_ANCHORS*100
    eligible_points=int(eligible_candidate_mask(selected,requirements).sum())
    candidates=rank_candidates(selected,suitability,requirements,request.limit)
    return {'candidates':candidates,'searched_points':selected.attrs.get('initial_grid_points',len(selected)),'measured_points':selected.attrs.get('earth_measured_points',len(selected)),'satellite_candidate_points':selected.attrs.get('satellite_candidate_points',len(selected)),'model_ranked_points':len(selected),'eligible_points':eligible_points,'requirements':requirements,'semantic':interpreted.get('semantic',{}),
            'search':{'center_lat':request.area.center_lat,'center_lon':request.area.center_lon,'radius_km':request.area.radius_km,
                      'fresh_grid':True,'earth_engine':'Dynamic World 10 m open/built probability','buildings':'OpenStreetMap mapped building centres'},
            'method':'Fresh cells inside the selected radius are measured with Earth Engine, screened for mapped buildings and hazards, then ranked by TabPFN and the interpreted preferences.',
            'limitation':'Open-land evidence is a remote-screening signal, not a land listing or proof of ownership, availability, or legal buildability.'}


@lru_cache(maxsize=1)
def speech_pipeline():
    try:
        import torch
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError('Install the optional local-ai dependencies to use voice input') from exc
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    return pipeline('automatic-speech-recognition',model='distil-whisper/distil-small.en',device=device)


def decode_speech_audio(path:Path):
    try:
        import imageio_ffmpeg
        import numpy as np
    except ImportError as exc:
        raise RuntimeError('Install the local-ai dependencies to use voice input') from exc
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(path),'-f','f32le','-ac','1','-ar','16000','pipe:1']
    result=subprocess.run(command,capture_output=True,check=False)
    if result.returncode or not result.stdout:
        raise ValueError('The recording could not be decoded. Record a short request and try again.')
    return {'raw':np.frombuffer(result.stdout,dtype=np.float32).copy(),'sampling_rate':16000}


@app.post('/api/transcribe')
async def transcribe(request:Request):
    content=await request.body()
    if not content:raise HTTPException(422,'Record a short English request first')
    content_type=request.headers.get('content-type','').lower()
    suffix=next((extension for media,extension in (
        ('webm','.webm'),('mp4','.m4a'),('m4a','.m4a'),('ogg','.ogg'),
        ('aiff','.aiff'),('aifc','.aifc'),('wav','.wav'),
    ) if media in content_type),'.wav')
    path=None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as handle:
            handle.write(content);path=Path(handle.name)
        result=speech_pipeline()(decode_speech_audio(path))
        return {'text':result.get('text','').strip(),'model':'distil-whisper/distil-small.en','processing':'local'}
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    finally:
        if path and path.exists():path.unlink()


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
    for kind in ['hospital','school','pharmacy','shop','park','bus_stop','bank']:
        facilities=geo['facilities'][geo['facilities'].kind==kind]
        if facilities.empty:continue
        indices,distance=facilities.sindex.nearest(point,return_distance=True,return_all=False)
        item=facilities.iloc[int(indices[1,0])]
        nearby.append({'kind':kind,'name':item['name'],'distance_m':round(float(distance[0])),
            'source':'OpenStreetMap point amenities','distance_type':'Straight-line; not travel distance'})
    road_indices,road_distance=geo['roads'].sindex.nearest(point,return_distance=True,return_all=False)
    road=geo['roads'].iloc[int(road_indices[1,0])]
    terrain={};errors=[]
    try:
        terrain=(indexed_values_near([(location.lon,location.lat)])[0]
                 if location.detail=='preview' else statewide_values(location.lon,location.lat,point))
    except Exception as exc:errors.append({'source':'Earth Engine','type':type(exc).__name__,'message':'Measurements unavailable; do not infer safety from missing data'})
    try:estimate=prediction(terrain,[(location.lon,location.lat)],location.detail)
    except Exception as exc:estimate={'status':'unavailable','reason':f'Model inference unavailable ({type(exc).__name__})'}
    outcome,reason=score_outcome(estimate)
    outline=gpd.GeoSeries([area],crs=32643).to_crs(4326).iloc[0]
    return {'location':location.model_dump(),'district':district.iloc[0]['name'] if len(district) else 'Kerala boundary area',
            'outcome':outcome,'reason':reason,'area':mapping(outline),'hazards':evidence,
            'terrain':[{'feature':name,'value':terrain.get(name),**STATEWIDE_CATALOG[name]} for name in STATEWIDE_FEATURES],
            'current_hazards':{'gsi_landslide_susceptibility':terrain.get('gsi_landslide_susceptibility'),
                'flood_levels_m':{str(period):terrain.get(f'flood_level_{period}yr_m') for period in (10,25,50,100,200,500)},
                'source':'GSI 2022 and KSDMA/UNEP historical flood-return rasters'},
            'nearby':nearby,'google_places':[],'road':{'distance_m':round(float(road_distance[0])),'kind':road.kind,'mapped_access':road.access,'caveat':'Mapped road proximity does not prove legal or emergency access'},
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
    try:
        rows=indexed_values_near(coordinates) if selection.detail=='preview' else statewide_values_many(coordinates,points)
    except Exception as exc:errors.append({'source':'Earth Engine','type':type(exc).__name__,'message':'Measurements unavailable; try again shortly'})
    satellite_coordinates=[coordinates[0]]*len(coordinates) if coordinates else []
    try:estimate=prediction(rows,satellite_coordinates,selection.detail) if rows else {'status':'unavailable','reason':'Measurements unavailable'}
    except Exception as exc:estimate={'status':'unavailable','reason':f'Model inference unavailable ({type(exc).__name__})'}
    outcome,reason=score_outcome(estimate)
    representative=rows[0] if rows else {}
    centroid=polygon.representative_point();districts=intersecting(geo['districts'],polygon)
    nearby=[]
    for kind in ['hospital','school','pharmacy','shop','park','bus_stop','bank']:
        facilities=geo['facilities'][geo['facilities'].kind==kind]
        if facilities.empty:continue
        indices,distance=facilities.sindex.nearest(centroid,return_distance=True,return_all=False);item=facilities.iloc[int(indices[1,0])]
        nearby.append({'kind':kind,'name':item['name'],'distance_m':round(float(distance[0])),'source':'OpenStreetMap','distance_type':'Straight-line from area centre'})
    road_indices,road_distance=geo['roads'].sindex.nearest(centroid,return_distance=True,return_all=False);road=geo['roads'].iloc[int(road_indices[1,0])]
    centroid_wgs=gpd.GeoSeries([centroid],crs=32643).to_crs(4326).iloc[0]
    return {'location':{'lat':centroid_wgs.y,'lon':centroid_wgs.x,'area_m2':round(polygon.area),'selection_type':'polygon','sample_count':len(points),'model':'terramind_tabpfn','detail':selection.detail},
            'district':', '.join(sorted(districts.name.unique())) if len(districts) else 'Kerala boundary area','outcome':outcome,'reason':reason,'area':mapping(polygon_wgs),'hazards':[],
            'terrain':[{'feature':name,'value':representative.get(name),**STATEWIDE_CATALOG[name]} for name in STATEWIDE_FEATURES],
            'nearby':nearby,'google_places':[],'road':{'distance_m':round(float(road_distance[0])),'kind':road.kind,'mapped_access':road.access,'caveat':'Mapped road proximity does not prove legal access'},
            'prediction':estimate,'errors':errors,'scope':f'{round(polygon.area):,} m² polygon sampled at {len(points)} locations; not a cadastral survey or construction clearance'}


def _warm_models():
    try:
        geography();candidate_index();building_tree()
        warm_point=gpd.GeoDataFrame({'point_id':['warmup']},geometry=[Point(76.27,9.93)],crs=4326)
        attach_gsi_landslide(warm_point,ROOT/'data')
        global earth_ready
        with earth_lock:
            if not earth_ready:initialize();earth_ready=True
        load_statewide_tabpfn();load_multimodal_bundle()
    except Exception:
        pass


if (ROOT/'web/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
