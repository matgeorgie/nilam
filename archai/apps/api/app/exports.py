from io import BytesIO
from html import escape
import json
from math import hypot
from .schemas import HouseLayout

COLORS={'bedroom':'#e5eafa','bathroom':'#dceef1','kitchen':'#efe9df','living':'#e5ebdf','dining':'#f2e9df','balcony':'#e2ece3','porch':'#e7ece5','veranda':'#e3ecdf','parking':'#e9e9ec','hall':'#f6f5f1','stair':'#eeece6'}

def wall_parts(layout,w):
    length=hypot(w.x2-w.x1,w.y2-w.y1)
    openings=sorted([(d.position,d.position+d.width,0,7) for d in layout.doors if d.wall==w.id]+[(v.position,v.position+v.width,3,7) for v in layout.windows if v.wall==w.id])
    parts=[];cursor=0
    for lo,hi,bottom,top in openings:
        if lo>cursor:parts.append((cursor,lo,0,9))
        if bottom:parts.append((lo,hi,0,bottom))
        parts.append((lo,hi,top,9));cursor=hi
    if cursor<length:parts.append((cursor,length,0,9))
    return parts

def svg_export(layout):
    gap=12;total=layout.floors*(layout.width+gap)
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5 -8 {total+2} {layout.length+18}" width="{total*16}" height="{(layout.length+18)*16}"><rect x="-5" y="-8" width="{total+2}" height="{layout.length+18}" fill="white"/>']
    for floor in range(layout.floors):
        parts.append(f'<g transform="translate({floor*(layout.width+gap)},0)"><text y="-4" font-family="sans-serif" font-size="1.4">ArchAI Â· Floor {floor} Â· {layout.width:g} Ã— {layout.length:g} ft</text>')
        for r in layout.rooms:
            if r.floor!=floor:continue
            polygon=' '.join(f'{x},{y}' for x,y in r.polygon)
            parts.append(f'<polygon points="{polygon}" fill="{COLORS.get(r.type,"#eee")}"/><text x="{r.x+r.width/2}" y="{r.y+r.height/2}" text-anchor="middle" font-family="sans-serif" font-size="0.85">{escape(r.name)}</text><text x="{r.x+r.width/2}" y="{r.y+r.height/2+1.4}" text-anchor="middle" font-family="sans-serif" font-size="0.65">{r.width:.1f} Ã— {r.height:.1f} ft</text>')
        from .stair_geometry import stair_boxes
        for stair in layout.stairs:
            if floor not in (stair.from_floor,stair.to_floor):continue
            for size,pos in stair_boxes(stair):
                parts.append(f'<rect x="{pos[0]-size[0]/2}" y="{pos[2]-size[2]/2}" width="{size[0]}" height="{size[2]}" fill="none" stroke="#777" stroke-width="0.08"/>')
        for w in layout.walls:
            if w.floor!=floor:continue
            length=hypot(w.x2-w.x1,w.y2-w.y1);dx=(w.x2-w.x1)/length;dy=(w.y2-w.y1)/length
            for a,b,bottom,top in wall_parts(layout,w):
                if bottom==0 and top==9:parts.append(f'<path d="M {w.x1+dx*a} {w.y1+dy*a} L {w.x1+dx*b} {w.y1+dy*b}" stroke="#283349" stroke-width="0.22"/>')
        for d in layout.doors:
            w=next(w for w in layout.walls if w.id==d.wall)
            if w.floor!=floor:continue
            length=hypot(w.x2-w.x1,w.y2-w.y1);dx=(w.x2-w.x1)/length;dy=(w.y2-w.y1)/length;x=w.x1+dx*d.position;y=w.y1+dy*d.position
            if d.kind=='vehicle':
                parts.append(f'<path d="M{x-dy*.13} {y+dx*.13} l{dx*d.width} {dy*d.width} M{x+dy*.13} {y-dx*.13} l{dx*d.width} {dy*d.width}" fill="none" stroke="#405861" stroke-width="0.1"/>')
            else:
                parts.append(f'<path d="M{x+dx*d.width} {y+dy*d.width} A{d.width} {d.width} 0 0 1 {x-dy*d.width} {y+dx*d.width} L{x} {y}" fill="none" stroke="#8a94a5" stroke-width="0.08"/>')
        for v in layout.windows:
            w=next(w for w in layout.walls if w.id==v.wall)
            if w.floor!=floor:continue
            length=hypot(w.x2-w.x1,w.y2-w.y1);dx=(w.x2-w.x1)/length;dy=(w.y2-w.y1)/length
            parts.append(f'<path d="M{w.x1+dx*v.position} {w.y1+dy*v.position} l{dx*v.width} {dy*v.width}" stroke="#6c9db5" stroke-width="0.2"/>')
        parts.append('</g>')
    parts.append(f'<text x="0" y="{layout.length+5}" font-family="sans-serif" font-size="0.85">Conceptual design. Qualified architect/engineer review required before construction.</text></svg>')
    return ''.join(parts).encode()

def drawing_export(layout,fmt):
    if fmt=='svg':return svg_export(layout),'image/svg+xml'
    # PDF/PNG use the same semantic geometry; no browser screenshot dependency.
    if fmt=='pdf':
        from reportlab.pdfgen.canvas import Canvas
        out=BytesIO();c=Canvas(out,pagesize=(700,900))
        for floor in range(layout.floors):
            scale=min(580/layout.width,730/layout.length)
            c.setFont('Helvetica',16);c.drawString(50,855,f'ArchAI / Floor {floor}')
            for r in layout.rooms:
                if r.floor!=floor:continue
                c.setFillColor(COLORS.get(r.type,'#eeeeee'));path=c.beginPath();path.moveTo(50+r.polygon[0][0]*scale,90+(layout.length-r.polygon[0][1])*scale)
                for x,y in r.polygon[1:]:path.lineTo(50+x*scale,90+(layout.length-y)*scale)
                path.close();c.drawPath(path,fill=1,stroke=0)
                c.setFillColor('#26334a');c.setFont('Helvetica',7);c.drawCentredString(50+(r.x+r.width/2)*scale,90+(layout.length-r.y-r.height/2)*scale,r.name)
                c.drawCentredString(50+(r.x+r.width/2)*scale,80+(layout.length-r.y-r.height/2)*scale,f'{r.width:.1f} x {r.height:.1f} ft')
            for w in layout.walls:
                if w.floor!=floor:continue
                length=hypot(w.x2-w.x1,w.y2-w.y1);dx=(w.x2-w.x1)/length;dy=(w.y2-w.y1)/length
                c.setStrokeColor('#26334a');c.setLineWidth(1.5)
                for a,b,lo,hi in wall_parts(layout,w):
                    if lo==0 and hi==9:c.line(50+(w.x1+dx*a)*scale,90+(layout.length-w.y1-dy*a)*scale,50+(w.x1+dx*b)*scale,90+(layout.length-w.y1-dy*b)*scale)
            from .stair_geometry import stair_boxes
            c.setStrokeColor('#777777');c.setLineWidth(.5)
            for stair in layout.stairs:
                if floor not in (stair.from_floor,stair.to_floor):continue
                for size,pos in stair_boxes(stair):
                    c.rect(50+(pos[0]-size[0]/2)*scale,90+(layout.length-pos[2]-size[2]/2)*scale,size[0]*scale,size[2]*scale,fill=0,stroke=1)
            c.setFont('Helvetica',8);c.drawString(50,45,'Conceptual design. Qualified architect/engineer review required before construction.');c.showPage()
        c.save();return out.getvalue(),'application/pdf'
    if fmt=='png':
        from PIL import Image,ImageDraw
        scale=14;gap=8;im=Image.new('RGB',(int((layout.width+gap)*layout.floors*scale),int((layout.length+gap)*scale)),'white');draw=ImageDraw.Draw(im)
        for r in layout.rooms:
            x=(r.x+r.floor*(layout.width+gap)+2)*scale;y=(r.y+2)*scale
            polygon=[((px+r.floor*(layout.width+gap)+2)*scale,(py+2)*scale) for px,py in r.polygon]
            draw.polygon(polygon,fill=COLORS.get(r.type,'#eeeeee'))
            draw.text((x+8,y+12),r.name,fill='#26334a');draw.text((x+8,y+28),f'{r.width:.1f} x {r.height:.1f} ft',fill='#26334a')
        for w in layout.walls:
            length=hypot(w.x2-w.x1,w.y2-w.y1);dx=(w.x2-w.x1)/length;dy=(w.y2-w.y1)/length
            shift=w.floor*(layout.width+gap)+2
            for a,b,lo,hi in wall_parts(layout,w):
                if lo==0 and hi==9:
                    draw.line(((w.x1+dx*a+shift)*scale,(w.y1+dy*a+2)*scale,
                               (w.x1+dx*b+shift)*scale,(w.y1+dy*b+2)*scale),
                              fill='#26334a',width=4 if w.exterior else 2)
        from .stair_geometry import stair_boxes
        for stair in layout.stairs:
            for floor in (stair.from_floor,stair.to_floor):
                shift=floor*(layout.width+gap)+2
                for size,pos in stair_boxes(stair):
                    draw.rectangle(((pos[0]-size[0]/2+shift)*scale,(pos[2]-size[2]/2+2)*scale,(pos[0]+size[0]/2+shift)*scale,(pos[2]+size[2]/2+2)*scale),outline='#777777',width=1)
        out=BytesIO();im.save(out,format='PNG');return out.getvalue(),'image/png'
    raise ValueError('Choose svg, png or pdf.')

def model_export(layout,fmt):
    import trimesh
    import numpy as np
    scene=trimesh.Scene()
    def cube(name,size,position,color):
        mesh=trimesh.creation.box(extents=size);mesh.apply_translation(position);mesh.visual.vertex_colors=color;scene.add_geometry(mesh,node_name=name)
    from shapely.geometry import Polygon
    from shapely.ops import triangulate
    for r in layout.rooms:
        if r.type=='stair':continue
        polygon=Polygon(r.polygon)
        vertices=[];faces=[]
        for triangle in triangulate(polygon):
            if not polygon.covers(triangle):continue
            face=[]
            for x,z in list(triangle.exterior.coords)[:3]:
                face.append(len(vertices));vertices.append([x,-z])
            faces.append(face)
        if not faces:raise ValueError('Room polygon cannot be triangulated.')
        mesh=trimesh.creation.extrude_triangulation(np.asarray(vertices),np.asarray(faces),height=.32)
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]))
        mesh.apply_translation([0,r.floor*10-.16,0]);mesh.visual.vertex_colors=[211,215,216,255]
        scene.add_geometry(mesh,node_name=r.id+'-floor')
    for w in layout.walls:
        length=hypot(w.x2-w.x1,w.y2-w.y1)
        if length<=0:raise ValueError('A wall must have nonzero length.')
        dx=(w.x2-w.x1)/length;dz=(w.y2-w.y1)/length
        for i,(a,b,lo,hi) in enumerate(wall_parts(layout,w)):
            if b<=a or hi<=lo:continue
            mesh=trimesh.creation.box(extents=[b-a,hi-lo,w.thickness])
            mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.arctan2(dz,dx),[0,1,0]))
            mesh.apply_translation([w.x1+dx*(a+b)/2,w.floor*10+(lo+hi)/2,w.y1+dz*(a+b)/2])
            mesh.visual.vertex_colors=[237,234,228,255];scene.add_geometry(mesh,node_name=w.id+f'-{i}')
    from .stair_geometry import stair_boxes
    for stair in layout.stairs:
        for i,(size,position) in enumerate(stair_boxes(stair)):
            cube(stair.id+str(i),size,position,[165,151,132,255])
    scene.apply_scale(.3048) # glTF units are metres; canonical layout is feet
    if fmt=='glb': return scene.export(file_type='glb'),'model/gltf-binary'
    if fmt=='gltf':
        import base64
        bundle=scene.export(file_type='gltf');doc=json.loads(bundle['model.gltf'])
        for buffer in doc.get('buffers',[]):buffer['uri']='data:application/octet-stream;base64,'+base64.b64encode(bundle[buffer['uri']]).decode()
        return json.dumps(doc).encode(),'model/gltf+json'
    raise ValueError('Choose glb or gltf.')
