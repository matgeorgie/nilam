import type {Project} from './types';
export const API=process.env.NEXT_PUBLIC_API_URL || (typeof window!=='undefined'&&window.location.port==='8000'?window.location.origin+'/design-api':'http://127.0.0.1:8001');
export class ApiError extends Error{readonly status:number;constructor(message:string,status:number){super(message);this.name='ApiError';this.status=status}}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
  let response:Response;
  try{response=await fetch(API+'/api'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}})}catch{throw new Error('Cannot reach the ArchAI server. Make sure the backend is running on port 8001.')}
  if(!response.ok){const error=await response.json().catch(()=>({detail:'Request failed.'}));throw new ApiError(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail),response.status)}
  return response.json();
}
export async function demo(){return api<Project>('/projects/demo',{method:'POST'})}
export async function download(id:string,format:string){const dimension=['glb','gltf'].includes(format)?'3d':'2d';const response=await fetch(`${API}/api/projects/${id}/export/${dimension}?format=${format}`);if(!response.ok){const error=await response.json();throw new Error(error.detail||'Export failed.')}const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=`archai-design.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
