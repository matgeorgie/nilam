import type {Layout,Specification} from './types';
export function guidedRequirements(spec:Specification,layout:Layout|null):Specification{
 if(!layout)return spec;
 const available=layout.rooms.filter(r=>!r.attached_to),used=new Set<string>();
 const rooms=spec.rooms.flatMap(req=>Array.from({length:req.count},(_,i)=>{
  const matching=available.filter(r=>!used.has(r.id)&&r.type===req.type&&(req.preferred_floor==null||r.floor===req.preferred_floor));
  const name=req.name+(req.count>1?` ${i+1}`:'');
  const room=matching.find(r=>r.name.toLowerCase()===name.toLowerCase())||matching[0];
  if(!room)return {...req,name,count:1};used.add(room.id);
  return {...req,name:room.name,count:1,preferred_floor:room.floor,attached_bathroom:layout.rooms.some(b=>b.attached_to===room.id)||req.attached_bathroom};
 }));
 return {...spec,rooms};
}
