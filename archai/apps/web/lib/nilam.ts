import type {SiteContext} from './types';

export const NILAM_URL=process.env.NEXT_PUBLIC_NILAM_URL || 'http://127.0.0.1:8000/';
export const DESIGN_BASE='/design';

export function siteFromSearch(search:string):SiteContext|null{
 const query=new URLSearchParams(search);
 if(query.get('source')!=='nilam')return null;
 const lat=Number(query.get('lat')),lon=Number(query.get('lon'));
 const district=query.get('district')?.trim()||'';
 const rawScore=query.get('score');
 const score=rawScore===null?null:Number(rawScore);
 if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat<8||lat>13||lon<74||lon>78||district.length<2||district.length>40||score!==null&&(!Number.isFinite(score)||score<0||score>100))return null;
 return {source:'nilam',lat,lon,district,suitability_percent:score};
}
