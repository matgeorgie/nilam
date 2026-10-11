"""CubiCasa5K pretrained segmentation followed by measured 3D-ready vectorization.
The neural model parses the image; extrusion and rendering use explicit geometry.
Imports remain drafts because inferred openings/topology require human review.
"""
import base64
from io import BytesIO
from pathlib import Path
from functools import lru_cache
import threading
import numpy as np
import torch
from PIL import Image, UnidentifiedImageError
from ..schemas import HouseLayout,RoomGeometry,Wall,Door,Window,Check
from .cubicasa.hg_furukawa_original import hg_furukawa_original
ROOT=Path(__file__).parent/'cubicasa'
LOCK=threading.Lock()
KINDS={3:'kitchen',4:'living',5:'bedroom',6:'bathroom',7:'hall',9:'utility',10:'parking',11:'office'}

@lru_cache(maxsize=1)
def model():
    checkpoint=ROOT/'model_best_val_loss_var.pkl'
    if not checkpoint.is_file():raise RuntimeError('CubiCasa weights are missing. Run scripts/setup-reconstruction.ps1 once.')
    network=hg_furukawa_original(44)
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    network.load_state_dict(state['model_state']);network.eval()
    return network

def reconstruct_image(encoded,image_width_feet):
    import cv2
    try:
        raw=base64.b64decode(encoded.split(',')[-1],validate=True)
        if len(raw)>8000000:raise ValueError('Use an image smaller than 8 MB.')
        image=Image.open(BytesIO(raw))
        if image.width*image.height>16000000:raise ValueError('Use an image below 16 megapixels.')
        if image.format not in ('PNG','JPEG'):raise ValueError('Use a PNG or JPEG floor plan.')
        image=image.convert('RGB')
    except (UnidentifiedImageError,base64.binascii.Error) as exc:raise ValueError('Invalid floor-plan image.') from exc
    width,height=image.size
    # Preserve aspect ratio: 512 square only pads; it never stretches the plan.
    factor=min(512/width,512/height);nw=max(1,round(width*factor));nh=max(1,round(height*factor))
    canvas=Image.new('RGB',(512,512),'white');canvas.paste(image.resize((nw,nh)),(0,0))
    tensor=torch.from_numpy(np.asarray(canvas).copy()).permute(2,0,1).float().unsqueeze(0)/127.5-1
    with LOCK,torch.inference_mode():prediction=model()(tensor)[0].numpy()
    labels=prediction[21:33,:nh,:nw].argmax(0);icons=prediction[33:44,:nh,:nw].argmax(0)
    scale=image_width_feet/nw
    layout=vectorize(labels,icons,scale)
    layout.width=image_width_feet;layout.length=nh*scale
    layout.generation_info={'model':'CubiCasa5K','loaded':True,'used':True,'scale':'user-supplied total image width','draft':True}
    return layout

def vectorize(labels,icons,scale):
    import cv2
    rooms=[];walls=[];doors=[];windows=[]
    for label,kind in KINDS.items():
        mask=(labels==label).astype('uint8')
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if cv2.contourArea(contour)<35:continue
            poly=cv2.approxPolyDP(contour,1.2,True).reshape(-1,2)
            if len(poly)<3:continue
            from shapely.geometry import Polygon
            shape=Polygon(poly*scale)
            if not shape.is_valid or shape.area<1:continue
            x,y,x1,y1=shape.bounds;index=sum(r.type==kind for r in rooms)+1
            rooms.append(RoomGeometry(id=f'import-{kind}-{index}',name=f'{kind.title()} {index}',type=kind,floor=0,
                x=x,y=y,width=x1-x,height=y1-y,polygon=[tuple(p) for p in (poly*scale).tolist()]))
    wall_mask=(labels==2).astype('uint8')
    # Retain measured wall thickness; directional morphology handles orthogonal plans.
    for horizontal in (True,False):
        kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(9,1) if horizontal else (1,9))
        spans=cv2.morphologyEx(wall_mask,cv2.MORPH_OPEN,kernel)
        contours,_=cv2.findContours(spans,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour)
            if (horizontal and (w<9 or w<h*2)) or (not horizontal and (h<9 or h<w*2)):continue
            coords=(x,y+h/2,x+w,y+h/2) if horizontal else (x+w/2,y,x+w/2,y+h)
            walls.append(Wall(id=f'import-wall-{len(walls)}',floor=0,x1=coords[0]*scale,y1=coords[1]*scale,x2=coords[2]*scale,y2=coords[3]*scale,
                thickness=max(.12,min(3,(h if horizontal else w)*scale))))
    from shapely.geometry import LineString,Point,Polygon
    for label in (1,2): # icon labels: window, door
        contours,_=cv2.findContours((icons==label).astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if cv2.contourArea(contour)<4 or not walls or not rooms:continue
            x,y,w,h=cv2.boundingRect(contour);center=Point((x+w/2)*scale,(y+h/2)*scale)
            wall=min(walls,key=lambda item:LineString([(item.x1,item.y1),(item.x2,item.y2)]).distance(center))
            line=LineString([(wall.x1,wall.y1),(wall.x2,wall.y2)])
            if line.distance(center)>max(1.5,wall.thickness*2):continue
            opening_width=min(max(w,h)*scale,line.length*.8)
            if opening_width<.5:continue
            position=max(0,min(line.length-opening_width,line.project(center)-opening_width/2))
            nearby=sorted(rooms,key=lambda room:Polygon(room.polygon).distance(center))
            if label==1:windows.append(Window(id=f'import-window-{len(windows)}',room=nearby[0].id,wall=wall.id,position=position,width=opening_width))
            else:doors.append(Door(id=f'import-door-{len(doors)}',room_a=nearby[0].id,room_b=nearby[1].id if len(nearby)>1 else None,
                wall=wall.id,position=position,width=opening_width))
    if not rooms or not walls:raise ValueError('No usable room/wall geometry detected. Use a clean orthogonal 2D floor plan, not a 3D render.')
    return HouseLayout(width=labels.shape[1]*scale,length=labels.shape[0]*scale,floors=1,rooms=rooms,walls=walls,doors=doors,windows=windows,stairs=[],
        strategy='CUBICASA_RECONSTRUCTION',checks=[Check(name='Imported image needs review',status='WARNING',
        detail='Room labels, openings and wall geometry are inferred. Total image width supplies scale; margins are included. Orthogonal plans only.')])
