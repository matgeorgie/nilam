"""Local HouseGAN++ proposals, independently validated before saving."""
from pathlib import Path
from time import perf_counter
import importlib.util
import threading
import numpy as np
import torch
from ..layout import LayoutEngine, build_walls, build_openings, validate, score, MIN_AREA
from ..schemas import HouseLayout, RoomGeometry

ROOT = Path(__file__).resolve().parent / 'houseganpp'
DEFAULT_CHECKPOINT = ROOT / 'checkpoints/pretrained.pth'
ROOM_CLASS = {'living':1,'kitchen':2,'bedroom':3,'bathroom':4,'balcony':5,
              'porch':6,'veranda':6,'dining':7,'office':8,'utility':10,'parking':6}

class MLGenerativeLayoutEngine(LayoutEngine):
    def __init__(self, model_path=None):
        self.device=torch.device('cpu') # tiny checkpoint; preserve VRAM for the viewer
        self.model_path=Path(model_path) if model_path else DEFAULT_CHECKPOINT
        self.is_loaded=False;self.model=None;self.load_error=None;self.lock=threading.Lock()
        try:
            module_spec=importlib.util.spec_from_file_location('archai_housegan_model',ROOT/'models/models.py')
            module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
            self.model=module.Generator().to(self.device)
            self.model.load_state_dict(torch.load(self.model_path,map_location=self.device,weights_only=True))
            self.model.eval();self.is_loaded=True
        except (ImportError,OSError,RuntimeError,ValueError) as exc:
            self.model=None;self.load_error=str(exc)

    @staticmethod
    def _room_instances(spec):
        counters={};instances=[]
        for requirement in spec.rooms:
            for index in range(requirement.count):
                ordinal=counters.get(requirement.type,0)+1;counters[requirement.type]=ordinal
                instances.append((f'{requirement.type}-{ordinal}',requirement))
        return instances

    def _spec_to_graph(self,spec,instances):
        nodes=torch.zeros((len(instances),18));edges=[]
        for i,(_,requirement) in enumerate(instances):nodes[i,ROOM_CLASS.get(requirement.type,16)-1]=1
        for i in range(len(instances)):
            for j in range(i+1,len(instances)):
                a_id,a=instances[i];b_id,b=instances[j]
                connected=any(rel.relation in ('connected','attached','accessible_from','adjacent','open_to') and
                    ((rel.source in (a_id,a.name,a.type) and rel.target in (b_id,b.name,b.type)) or
                     (rel.target in (a_id,a.name,a.type) and rel.source in (b_id,b.name,b.type))) for rel in spec.relationships)
                edges.append([i,1 if connected else -1,j])
        return nodes,torch.tensor(edges,dtype=torch.long).reshape(-1,3)

    def _proposal(self,spec,instances,attempt):
        nodes,edges=self._spec_to_graph(spec,instances)
        rng=torch.Generator(device='cpu').manual_seed(2301+attempt)
        z=torch.randn(len(instances),128,generator=rng)
        given=torch.zeros(len(instances),2,64,64);given[:,0]=-1
        with self.lock,torch.inference_mode():masks=self.model(z,given,nodes,edges).numpy()
        unit_scale=3.280839895 if spec.unit=='meters' else 1
        width=spec.plot_width*unit_scale;length=spec.plot_length*unit_scale
        # Existing canonical geometry is always feet, including metric requests.
        from ..footprint import generate_footprint
        setbacks=spec.setbacks.model_copy(deep=True)
        for field in ('front_setback','rear_setback','left_setback','right_setback'):
            setattr(setbacks,field,getattr(setbacks,field)*unit_scale)
        footprint=generate_footprint('rectangle',width,length,{},setbacks)
        x0,y0,x1,y1=footprint.bounding_box
        rooms=[]
        for i,(room_id,requirement) in enumerate(instances):
            ys,xs=np.where(masks[i]>0)
            if not len(xs):raise ValueError('Empty room mask')
            xa=x0+xs.min()/64*(x1-x0);xb=x0+(xs.max()+1)/64*(x1-x0)
            ya=y0+ys.min()/64*(y1-y0);yb=y0+(ys.max()+1)/64*(y1-y0)
            rooms.append(RoomGeometry(id=room_id,name=requirement.name+(f' {i+1}' if requirement.count>1 else ''),type=requirement.type,
                floor=0,x=xa,y=ya,width=xb-xa,height=yb-ya,
                minimum_area=max(MIN_AREA.get(requirement.type,0),(requirement.minimum_area or 0)*unit_scale**2)))
        layout=HouseLayout(width=width,length=length,floors=1,footprint=footprint,
            plot_boundary=[(0,0),(width,0),(width,length),(0,length)],setback_boundary=footprint.buildable_boundary or [],
            rooms=rooms,walls=[],doors=[],windows=[],stairs=[],strategy='HOUSEGAN')
        build_walls(layout,spec);build_openings(layout,spec)
        checks=validate(layout,spec)
        errors=[c.name for c in checks if c.status=='ERROR']
        if errors:raise ValueError(', '.join(errors))
        layout.checks=checks;layout.score=score(layout,spec);return layout

    def generate(self,spec,evaluator=None):
        started=perf_counter();rejections=[];attempts=0
        eligible=spec.floors==1 and spec.shape in ('auto','rectangle') and not spec.plot_polygon and not any(r.attached_bathroom for r in spec.rooms)
        instances=self._room_instances(spec)
        if self.is_loaded and eligible and 2<=len(instances)<=12:
            for attempt in range(3):
                attempts+=1
                try:
                    layout=self._proposal(spec,instances,attempt)
                    if evaluator:
                        checks,_=evaluator(layout)
                        if any(c.status=='ERROR' for c in checks):raise ValueError('Spatial intent failed')
                    layout.generation_info={'model':'HouseGAN++','loaded':True,'used':True,'attempts':attempts,'rejections':rejections}
                    layout.generation_ms=(perf_counter()-started)*1000;return layout
                except (ValueError,RuntimeError,IndexError) as exc:rejections.append(str(exc))
        from ..simple_home import SimpleHomeLayoutEngine
        layout=SimpleHomeLayoutEngine().generate(spec,evaluator)
        layout.generation_info={'model':'HouseGAN++','loaded':self.is_loaded,'used':False,'attempts':attempts,
            'reason':self.load_error or ('Unsupported brief for single-floor learned proposal' if not eligible else 'No learned proposal passed validation'),
            'rejections':rejections,'final_engine':layout.strategy}
        layout.generation_ms=(perf_counter()-started)*1000
        return layout
