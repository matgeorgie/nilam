from io import BytesIO
import base64
import numpy as np
import torch
import trimesh
from shapely.geometry import Polygon
from app.schemas import HouseLayout,RoomGeometry,Wall,HouseSpecification,RoomRequirement
from app.ml.engine import MLGenerativeLayoutEngine
from app.ml.reconstruction import vectorize,reconstruct_image
from app.exports import model_export

def test_bundled_housegan_checkpoint_and_training_class_encoding():
    torch.set_num_threads(2)
    engine=MLGenerativeLayoutEngine()
    assert engine.is_loaded,engine.load_error
    spec=HouseSpecification(plot_width=40,plot_length=60,floors=1,rooms=[RoomRequirement(type='living',name='Living'),RoomRequirement(type='bedroom',name='Bedroom')])
    nodes,edges=engine._spec_to_graph(spec,engine._room_instances(spec))
    assert nodes[0].argmax().item()==0 # official dataset one-hot drops background
    assert nodes[1].argmax().item()==2
    assert len(edges)==1 # official CMP adds reverse edges itself
    layout=engine.generate(spec)
    assert layout.generation_info['loaded'] is True
    assert layout.generation_info['attempts']>0
    assert not [check for check in layout.checks if check.status=='ERROR']

def test_polygon_and_diagonal_wall_export_preserve_geometry_and_metric_scale():
    room=RoomGeometry(id='r',name='Room',type='living',floor=0,x=0,y=0,width=6,height=6,polygon=[(0,0),(6,0),(6,2),(2,2),(2,6),(0,6)])
    wall=Wall(id='diagonal',floor=0,x1=0,y1=0,x2=3,y2=4,thickness=.5)
    layout=HouseLayout(width=6,length=6,floors=1,rooms=[room],walls=[wall],doors=[],windows=[],stairs=[])
    data,_=model_export(layout,'glb');scene=trimesh.load(BytesIO(data),file_type='glb',force='scene')
    meshes=list(scene.dump());floor=next(m for m in meshes if m.vertices[:,1].max()<.1)
    assert abs(abs(floor.volume)-20*.32*.3048**3)<1e-6
    assert abs(floor.bounds[1,0]-6*.3048)<1e-6
    wallmesh=next(m for m in meshes if m.vertices[:,1].max()>1)
    assert abs(abs(wallmesh.volume)-5*9*.5*.3048**3)<1e-5

def test_segmentation_vectorization_keeps_room_polygons_and_wall_thickness():
    labels=np.zeros((100,100),dtype=np.uint8);labels[12:88,12:88]=5
    labels[8:12,8:92]=2;labels[88:92,8:92]=2;labels[8:92,8:12]=2;labels[8:92,88:92]=2
    layout=vectorize(labels,np.zeros_like(labels),.5)
    assert len(layout.rooms)==1 and len(layout.walls)==4
    assert Polygon(layout.rooms[0].polygon).area>1000
    assert all(abs(w.thickness-2)<.01 for w in layout.walls)
    assert layout.checks[0].status=='WARNING'

def test_real_cubicasa_checkpoint_reconstructs_clean_floorplan():
    from pathlib import Path
    image=Path(__file__).resolve().parent/'fixtures/clean-floorplan.png'
    torch.set_num_threads(2)
    layout=reconstruct_image(base64.b64encode(image.read_bytes()).decode(),40)
    assert layout.generation_info['model']=='CubiCasa5K'
    assert layout.rooms and layout.walls
    assert all(Polygon(room.polygon).is_valid for room in layout.rooms)
