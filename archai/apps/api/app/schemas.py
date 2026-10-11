from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class RoomCategory(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SERVICE = "service"
    CIRCULATION = "circulation"

class RoomEnclosure(str, Enum):
    ENCLOSED = "enclosed"
    OPEN = "open"
    SEMI_OPEN = "semi_open"

class ArchitecturalRelation(str, Enum):
    ADJACENT = "adjacent"
    NEAR = "near"
    CONNECTED = "connected"
    OPEN_TO = "open_to"
    AWAY_FROM = "away_from"
    ACCESSED_FROM = "accessed_from"
    SEPARATED = "separated"
    ATTACHED = "attached"
    PREFERRED_NEAR = "preferred_near"
    MUST_NOT_BE_ADJACENT = "must_not_be_adjacent"
    ACCESSIBLE_FROM = "accessible_from"

DEFAULT_ROOM_CATEGORIES: dict[str, RoomCategory] = {
    'living': RoomCategory.PUBLIC,
    'dining': RoomCategory.PUBLIC,
    'porch': RoomCategory.PUBLIC,
    'veranda': RoomCategory.PUBLIC,
    'bedroom': RoomCategory.PRIVATE,
    'attached_bathroom': RoomCategory.PRIVATE,
    'office': RoomCategory.PRIVATE,
    'kitchen': RoomCategory.SERVICE,
    'utility': RoomCategory.SERVICE,
    'bathroom': RoomCategory.SERVICE,
    'common_bathroom': RoomCategory.SERVICE,
    'parking': RoomCategory.SERVICE,
    'hall': RoomCategory.CIRCULATION,
    'stair': RoomCategory.CIRCULATION,
}

def default_room_category(room_type: str) -> RoomCategory:
    return DEFAULT_ROOM_CATEGORIES.get(room_type.lower(), RoomCategory.PRIVATE)

class RoomRequirement(StrictModel):
    type: Literal['bedroom','bathroom','kitchen','dining','living','parking','balcony','office','utility','porch','veranda']
    name: str = Field(min_length=1, max_length=100)
    count: int = Field(default=1, ge=1, le=30)
    minimum_area: float | None = Field(default=None, gt=0)
    preferred_area: float | None = Field(default=None, gt=0)
    attached_bathroom: bool = False
    preferred_floor: int | None = Field(default=None, ge=0, le=3)
    exact_width: float | None = Field(default=None, gt=0)
    exact_length: float | None = Field(default=None, gt=0)
    category: RoomCategory | None = None
    enclosure: RoomEnclosure | None = None

class Relationship(StrictModel):
    source: str
    target: str
    relation: ArchitecturalRelation | Literal['adjacent','near','connected','separated','accessible_from','attached','preferred_near','must_not_be_adjacent','open_to','away_from','accessed_from']

class HouseShape(str, Enum):
    AUTO = "auto"
    RECTANGLE = "rectangle"
    L_SHAPE = "l_shape"
    T_SHAPE = "t_shape"
    U_SHAPE = "u_shape"
    C_SHAPE = "c_shape"
    STEPPED = "stepped"
    COURTYARD = "courtyard"

class SiteConstraints(StrictModel):
    front_setback: float = Field(default=0, ge=0, le=100)
    rear_setback: float = Field(default=0, ge=0, le=100)
    left_setback: float = Field(default=0, ge=0, le=100)
    right_setback: float = Field(default=0, ge=0, le=100)

class RoomReference(StrictModel):
    name: str | None = None
    type: str | None = None
    ordinal: int | None = Field(default=None, ge=1)
    target_all: bool = False

    @model_validator(mode='after')
    def identifiable(self):
        if not self.name and not self.type:
            raise ValueError('A room reference needs a name or type.')
        return self

class SpatialConstraint(StrictModel):
    kind: Literal['floor_placement','minimum_area','relationship','setbacks','parking_access']
    priority: Literal['hard','soft']
    source_text: str = Field(min_length=1)
    room: RoomReference | None = None
    target: RoomReference | None = None
    floor: int | None = Field(default=None, ge=0, le=3)
    area: float | None = Field(default=None, gt=0)
    relation: ArchitecturalRelation | Literal['adjacent','near','connected','separated','accessible_from','attached','preferred_near','must_not_be_adjacent','open_to','away_from','accessed_from'] | None = None
    setbacks: SiteConstraints | None = None
    road_side: Literal['north','south','east','west'] | None = None

    @model_validator(mode='after')
    def required_fields(self):
        needed={
            'floor_placement': self.room is not None and self.floor is not None,
            'minimum_area': self.room is not None and self.area is not None,
            'relationship': self.room is not None and self.target is not None and self.relation is not None,
            'setbacks': self.setbacks is not None,
            'parking_access': self.road_side is not None,
        }
        if not needed[self.kind]:
            raise ValueError(f'{self.kind} is missing required typed fields.')
        return self

class UnsupportedRequest(StrictModel):
    text: str = Field(min_length=1)
    requested_priority: Literal['hard','soft']
    reason: str = Field(min_length=1)

class RoomRelationship(StrictModel):
    source: RoomReference
    target: RoomReference
    relation: ArchitecturalRelation
    priority: Literal['hard','soft'] = 'hard'

class SpatialIntent(StrictModel):
    version: Literal[1] = 1
    constraints: list[SpatialConstraint] = Field(default_factory=list)
    unsupported_requests: list[UnsupportedRequest] = Field(default_factory=list)
    room_categories: dict[str, RoomCategory] = Field(default_factory=dict)
    room_enclosures: dict[str, RoomEnclosure] = Field(default_factory=dict)
    architectural_relationships: list[RoomRelationship] = Field(default_factory=list)

class ArchitecturalLayoutIntent(SpatialIntent):
    pass

class SiteContext(StrictModel):
    source: Literal['nilam'] = 'nilam'
    lat: float = Field(ge=8.0, le=13.0)
    lon: float = Field(ge=74.0, le=78.0)
    district: str = Field(min_length=2, max_length=40)
    suitability_percent: float | None = Field(default=None, ge=0, le=100)

class HouseSpecification(StrictModel):
    plot_width: float | None = Field(default=None, gt=0, le=300)
    plot_length: float | None = Field(default=None, gt=0, le=300)
    plot_polygon: list[tuple[float, float]] | None = Field(default=None, min_length=3)
    shape: HouseShape = HouseShape.AUTO
    shape_parameters: dict[str, float] = Field(default_factory=dict)
    setbacks: SiteConstraints = Field(default_factory=SiteConstraints)
    unit: Literal['feet','meters'] = 'feet'
    floors: int | None = Field(default=None, ge=1, le=4)
    orientation: Literal['north','south','east','west'] = 'north'
    north_angle: float = Field(default=0, ge=0, lt=360)
    road_location: Literal['north','south','east','west'] = 'south'
    road_width: float | None = Field(default=None, gt=0, le=200)
    rooms: list[RoomRequirement] = Field(default_factory=list, max_length=50)
    parking_spaces: int = Field(default=0, ge=0, le=4)
    style: str | None = None
    special_requirements: list[str] = Field(default_factory=list)
    preferences: dict[str, str | float | bool] = Field(default_factory=dict)
    relationships: list[Relationship] = Field(default_factory=list)
    provenance: dict[str, Literal['user','system_default','ai_assumption']] = Field(default_factory=dict)
    site_context: SiteContext | None = None
    spatial_intent: ArchitecturalLayoutIntent | SpatialIntent | None = None

    @model_validator(mode='before')
    @classmethod
    def migrate_shape(cls, data):
        if isinstance(data, dict) and 'shape' in data:
            legacy_map = {'rectangle': 'rectangle', 'L-shape': 'l_shape', 'U-shape': 'u_shape', 'T-shape': 't_shape'}
            if data['shape'] in legacy_map:
                data['shape'] = legacy_map[data['shape']]
            if isinstance(data.get('provenance'),dict):
                data['provenance']={key:('user' if value=='candidate_selection' else value) for key,value in data['provenance'].items()}
        return data

    @model_validator(mode='after')
    def check_floors(self):
        if self.floors and any(r.preferred_floor is not None and r.preferred_floor >= self.floors for r in self.rooms):
            raise ValueError('A requested room floor does not exist.')
        return self

class HouseFootprint(StrictModel):
    shape: HouseShape
    plot_width: float
    plot_length: float
    boundary: list[tuple[float, float]]
    courtyard: list[tuple[float, float]] | None = None
    buildable_boundary: list[tuple[float, float]] | None = None
    bounding_box: tuple[float, float, float, float]
    metrics: dict[str, float] = Field(default_factory=dict)

class RoomGeometry(StrictModel):
    id: str
    name: str
    type: str
    floor: int
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    polygon: list[tuple[float, float]] = Field(default_factory=list)
    rotation: float = 0
    attached_to: str | None = None
    minimum_area: float = 0
    preferred_area: float | None = None
    privacy_level: Literal['public','semi_private','private','service'] = 'semi_private'
    accessible: bool = True

    @model_validator(mode='after')
    def ensure_polygon(self):
        if not self.polygon:
            self.polygon=[(self.x,self.y),(self.x+self.width,self.y),(self.x+self.width,self.y+self.height),(self.x,self.y+self.height)]
        if len(self.polygon)<3:
            raise ValueError('Room polygon requires at least three vertices.')
        xs=[p[0] for p in self.polygon];ys=[p[1] for p in self.polygon]
        self.x=min(xs);self.y=min(ys);self.width=max(xs)-self.x;self.height=max(ys)-self.y
        return self

class Wall(StrictModel):
    id: str
    floor: int
    x1: float
    y1: float
    x2: float
    y2: float
    exterior: bool = False
    thickness: float = Field(default=0.5, gt=0, le=3)

class Door(StrictModel):
    id: str
    room_a: str
    room_b: str | None
    wall: str
    position: float
    width: float = 2.6
    swing_direction: Literal['left','right'] = 'left'
    kind: Literal['interior','entry','vehicle','courtyard'] = 'interior'

class Window(StrictModel):
    id: str
    room: str
    wall: str
    position: float
    width: float = 3

class Stair(StrictModel):
    id: str
    from_floor: int
    to_floor: int
    x: float
    y: float
    width: float = Field(gt=0)
    length: float = Field(gt=0)
    direction: Literal['north','south','east','west'] = 'north'
    kind: Literal['straight', 'dogleg'] = 'straight'
    landing_depth: float = Field(default=4.0, ge=3.5, le=10)
    risers: int = Field(default=18, ge=16, le=32, multiple_of=2)

class Check(StrictModel):
    name: str
    status: Literal['PASS','WARNING','ERROR']
    detail: str

class LayoutScore(StrictModel):
    requirement_score: float
    adjacency_score: float
    area_score: float
    circulation_score: float
    efficiency_score: float
    lighting_score: float
    privacy_score: float = 100
    ventilation_score: float = 100
    structural_score: float = 100
    plot_utilization_score: float = 100
    strategy_score: float = 100
    overall_score: float

class LayoutAlternative(StrictModel):
    candidate_id: str
    strategy: str = 'UNKNOWN'
    label: str
    rationale: str
    width: float
    length: float
    floors: int
    unit: Literal['feet'] = 'feet'
    footprint: HouseFootprint
    rooms: list[RoomGeometry]
    walls: list[Wall]
    doors: list[Door]
    windows: list[Window]
    stairs: list[Stair]
    checks: list[Check]
    score: LayoutScore

class HouseLayout(StrictModel):
    generation_info: dict = Field(default_factory=dict)
    width: float
    length: float
    floors: int
    unit: Literal['feet'] = 'feet'
    footprint: HouseFootprint | None = None
    plot_boundary: list[tuple[float, float]] = Field(default_factory=list)
    setback_boundary: list[tuple[float, float]] = Field(default_factory=list)
    road_edge: tuple[tuple[float, float], tuple[float, float]] | None = None
    strategy: str = 'UNKNOWN'
    rooms: list[RoomGeometry]
    walls: list[Wall]
    doors: list[Door]
    windows: list[Window]
    stairs: list[Stair]
    checks: list[Check] = Field(default_factory=list)
    score: LayoutScore | None = None
    generation_ms: float = 0
    candidate_count: int = 0
    chosen_candidate_id: str | None = None
    alternatives: list[LayoutAlternative] = Field(default_factory=list)

class Operation(StrictModel):
    operation: Literal['set_house_shape','change_shape_parameters','add_room','remove_room','resize_room','move_room','connect_rooms','disconnect_rooms','change_floor','add_door','remove_door','add_window','remove_window','add_balcony','change_style','change_plot','regenerate_layout','swap_rooms']
    target_room: str | None = None
    shape: HouseShape | None = None
    parameters: dict[str, str | float | int | bool] = Field(default_factory=dict)

class Extraction(StrictModel):
    specification: HouseSpecification
    explanation: str
    spatial_intent: SpatialIntent | None = None

class LLMExtraction(Extraction):
    spatial_intent: SpatialIntent
