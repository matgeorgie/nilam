from .schemas import HouseSpecification, Operation, RoomRequirement, Relationship
from .layout import MIN_AREA

def apply_operation(spec: HouseSpecification, op: Operation, layout=None) -> HouseSpecification:
    data=spec.model_copy(deep=True)
    p=op.parameters
    matches=[r for r in data.rooms if op.target_room and op.target_room.lower() in (r.name.lower(),r.type.lower())]
    if op.operation=='add_room' or op.operation=='add_balcony':
        kind=str(p.get('type','balcony' if op.operation=='add_balcony' else 'bedroom'))
        name=str(p.get('name',kind.capitalize()))
        if any(r.name==name for r in data.rooms): name+=f' {sum(r.count for r in data.rooms if r.type==kind)+1}'
        data.rooms.append(RoomRequirement(type=kind,name=name,count=int(p.get('count',1)),preferred_floor=int(p['floor']) if 'floor' in p else None,attached_bathroom=bool(p.get('attached_bathroom',False))))
    elif op.operation=='remove_room':
        if not matches: raise ValueError('Which room would you like to remove?')
        if matches[0].count>1: matches[0].count-=1
        else: data.rooms.remove(matches[0])
    elif op.operation=='resize_room':
        if not matches: raise ValueError('Which room would you like to resize?')
        room=matches[0]
        if 'width' in p and 'length' in p:
            room.exact_width=float(p['width']);room.exact_length=float(p['length']);room.preferred_area=room.exact_width*room.exact_length
        else:
            scale=3.280839895 if data.unit=='meters' else 1
            current=next((r.width*r.height/scale**2 for r in layout.rooms if r.name==room.name),None) if layout else None
            room.preferred_area=float(p.get('area',(current or room.preferred_area or MIN_AREA[room.type]*1.25/scale**2)*float(p.get('factor',1.2))))
            room.minimum_area=room.preferred_area
    elif op.operation=='change_floor': data.floors=int(p['floors'])
    elif op.operation=='move_room':
        if not matches or 'floor' not in p: raise ValueError('Specify a room and target floor. Free coordinate movement is not supported by this optimizer.')
        matches[0].preferred_floor=int(p['floor'])
    elif op.operation=='set_house_shape':
        new_shape = op.shape or p.get('shape')
        if new_shape:
            data.shape = new_shape
            data.provenance['shape'] = 'user'
    elif op.operation=='change_shape_parameters':
        data.shape_parameters.update(p)
    elif op.operation=='change_plot': data.plot_width=float(p['width']);data.plot_length=float(p['length'])
    elif op.operation=='change_style': data.style=str(p['style'])
    elif op.operation=='connect_rooms': data.relationships.append(Relationship(source=op.target_room or '',target=str(p['target']),relation=str(p.get('relation','connected'))))
    elif op.operation=='disconnect_rooms': data.relationships=[r for r in data.relationships if not (r.source==op.target_room and r.target==p.get('target'))]
    elif op.operation!='regenerate_layout': raise ValueError('Individual opening edits need a wall-specific geometry editor. This operation is not yet supported; no changes were applied.')
    data.provenance['last_modification']='user'
    return HouseSpecification.model_validate(data.model_dump())

def demo_spec():
    return HouseSpecification(plot_width=30,plot_length=50,shape='auto',floors=2,parking_spaces=1,style='Modern',rooms=[
        RoomRequirement(type='bedroom',name='Master bedroom',attached_bathroom=True,preferred_floor=1),
        RoomRequirement(type='bedroom',name='Bedroom 2',attached_bathroom=True,preferred_floor=1),
        RoomRequirement(type='bedroom',name='Guest bedroom',attached_bathroom=True,preferred_floor=0),
        RoomRequirement(type='bedroom',name='Bedroom 4',preferred_floor=1),
        RoomRequirement(type='bathroom',name='Common bathroom',preferred_floor=0),
        RoomRequirement(type='kitchen',name='Kitchen',preferred_floor=0),
        RoomRequirement(type='dining',name='Dining',preferred_floor=0),
        RoomRequirement(type='living',name='Living room',preferred_floor=0),
        RoomRequirement(type='balcony',name='Balcony',count=2,preferred_floor=1),
    ],relationships=[Relationship(source='kitchen',target='dining',relation='connected')],provenance={'rooms':'user','plot_width':'user','plot_length':'user','floors':'user','minimum_room_areas':'system_default','orientation':'system_default'})
