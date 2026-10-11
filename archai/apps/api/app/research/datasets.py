"""Dataset adapters normalize licensed source geometry; they never download data."""
from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Literal
from pydantic import Field
from ..schemas import StrictModel, RoomGeometry
from ..layout import bounds


class DatasetSample(StrictModel):
    source: Literal['cubicasa5k','rplan','structured3d','houseexpo','resplan','msd','custom']
    sample_id: str
    license_reference: str
    units: Literal['feet','meters'] = 'feet'
    footprint: list[tuple[float,float]] | None = None
    rooms: list[RoomGeometry] = Field(min_length=1)
    walls: list[list[tuple[float,float]]] = Field(default_factory=list)
    openings: list[dict] = Field(default_factory=list)


class DatasetAdapter(ABC):
    """Explicit trust boundary between third-party annotations and ArchAI geometry."""
    source: str
    @abstractmethod
    def load(self,path:Path) -> DatasetSample: ...

    def validate(self,sample:DatasetSample) -> DatasetSample:
        for i,a in enumerate(sample.rooms):
            if not bounds(a).is_valid or bounds(a).area<=0:
                raise ValueError(f'Invalid room polygon: {a.id}')
            for b in sample.rooms[i+1:]:
                if a.floor==b.floor and bounds(a).intersection(bounds(b)).area>1e-5:
                    raise ValueError(f'Overlapping dataset labels: {a.id}, {b.id}')
        return sample


class NormalizedJSONAdapter(DatasetAdapter):
    source='custom'
    def load(self,path:Path) -> DatasetSample:
        return self.validate(DatasetSample.model_validate_json(path.read_text(encoding='utf-8')))


class HouseExpoAdapter(DatasetAdapter):
    """Normalize one HouseExpo JSON record without importing raster imagery."""
    source='houseexpo'
    def load(self,path:Path) -> DatasetSample:
        raw=json.loads(path.read_text(encoding='utf-8'))
        rooms=[]
        for index,(kind,bbox) in enumerate(raw.get('room_category',{}).items()):
            values=bbox if isinstance(bbox,list) and len(bbox)==4 else None
            if not values: continue
            x1,y1,x2,y2=map(float,values)
            rooms.append(RoomGeometry(id=f'{kind}-{index+1}',name=f'{kind.title()} {index+1}',type=kind.lower(),floor=0,x=x1,y=y1,width=x2-x1,height=y2-y1))
        sample=DatasetSample(source='houseexpo',sample_id=str(raw.get('id',path.stem)),license_reference='HouseExpo repository MIT license; verify upstream SUNCG provenance before commercial training.',units='meters',footprint=[tuple(map(float,p)) for p in raw.get('verts',[])],rooms=rooms)
        return self.validate(sample)


def load_normalized_sample(path:Path) -> DatasetSample:
    return NormalizedJSONAdapter().load(path)
