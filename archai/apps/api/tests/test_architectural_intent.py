"""Phase 1 unit tests for Architectural Intent Data Model."""
import pytest
from pydantic import ValidationError

from app.ai.intent import compile_intent
from app.schemas import (ArchitecturalLayoutIntent, ArchitecturalRelation, HouseSpecification,
                         Relationship, RoomCategory, RoomEnclosure, RoomReference,
                         RoomRelationship, RoomRequirement, SpatialConstraint, SpatialIntent,
                         default_room_category)


def test_room_category_and_defaults():
    assert RoomCategory.PUBLIC.value == 'public'
    assert RoomCategory.PRIVATE.value == 'private'
    assert RoomCategory.SERVICE.value == 'service'
    assert RoomCategory.CIRCULATION.value == 'circulation'

    assert default_room_category('living') == RoomCategory.PUBLIC
    assert default_room_category('dining') == RoomCategory.PUBLIC
    assert default_room_category('bedroom') == RoomCategory.PRIVATE
    assert default_room_category('office') == RoomCategory.PRIVATE
    assert default_room_category('kitchen') == RoomCategory.SERVICE
    assert default_room_category('bathroom') == RoomCategory.SERVICE
    assert default_room_category('parking') == RoomCategory.SERVICE
    assert default_room_category('hall') == RoomCategory.CIRCULATION
    assert default_room_category('stair') == RoomCategory.CIRCULATION
    assert default_room_category('unknown_space') == RoomCategory.PRIVATE


def test_room_enclosure_values():
    assert RoomEnclosure.ENCLOSED.value == 'enclosed'
    assert RoomEnclosure.OPEN.value == 'open'
    assert RoomEnclosure.SEMI_OPEN.value == 'semi_open'


def test_architectural_relation_values():
    assert ArchitecturalRelation.OPEN_TO.value == 'open_to'
    assert ArchitecturalRelation.AWAY_FROM.value == 'away_from'
    assert ArchitecturalRelation.ACCESSED_FROM.value == 'accessed_from'
    assert ArchitecturalRelation.CONNECTED.value == 'connected'
    assert ArchitecturalRelation.ADJACENT.value == 'adjacent'


def test_room_relationship_validation():
    rel = RoomRelationship(
        source=RoomReference(type='living'),
        target=RoomReference(type='dining'),
        relation=ArchitecturalRelation.OPEN_TO,
        priority='hard'
    )
    assert rel.source.type == 'living'
    assert rel.target.type == 'dining'
    assert rel.relation == ArchitecturalRelation.OPEN_TO
    assert rel.priority == 'hard'

    with pytest.raises(ValidationError):
        RoomRelationship(
            source=RoomReference(type='living'),
            target=RoomReference(type='dining'),
            relation=ArchitecturalRelation.OPEN_TO,
            extra_field='invalid'
        )


def test_architectural_layout_intent_instantiation():
    intent = ArchitecturalLayoutIntent(
        room_categories={'living-1': RoomCategory.PUBLIC, 'bedroom-1': RoomCategory.PRIVATE},
        room_enclosures={'living-1': RoomEnclosure.OPEN, 'dining-1': RoomEnclosure.OPEN},
        architectural_relationships=[
            RoomRelationship(
                source=RoomReference(type='living'),
                target=RoomReference(type='dining'),
                relation=ArchitecturalRelation.OPEN_TO
            )
        ]
    )
    assert intent.room_categories['living-1'] == RoomCategory.PUBLIC
    assert intent.room_enclosures['living-1'] == RoomEnclosure.OPEN
    assert len(intent.architectural_relationships) == 1
    assert intent.architectural_relationships[0].relation == 'open_to'


def test_room_specific_floor_constraints():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='bedroom', name='Master bedroom'),
            RoomRequirement(type='bedroom', name='Guest bedroom'),
            RoomRequirement(type='bedroom', name='Kids bedroom'),
            RoomRequirement(type='living', name='Living room')
        ]
    )

    intent = SpatialIntent(constraints=[
        SpatialConstraint(
            kind='floor_placement',
            priority='hard',
            source_text='Master bedroom upstairs',
            room=RoomReference(name='Master bedroom'),
            floor=1
        ),
        SpatialConstraint(
            kind='floor_placement',
            priority='hard',
            source_text='Guest bedroom ground floor',
            room=RoomReference(name='Guest bedroom'),
            floor=0
        )
    ])

    compiled = compile_intent(spec, intent)
    rooms_by_name = {r.name: r for r in compiled.specification.rooms}

    # Master bedroom -> Floor 1
    assert rooms_by_name['Master bedroom'].preferred_floor == 1
    # Guest bedroom -> Floor 0
    assert rooms_by_name['Guest bedroom'].preferred_floor == 0
    # Kids bedroom -> Flexible (None)
    assert rooms_by_name['Kids bedroom'].preferred_floor is None


def test_target_all_bulk_room_floor_constraints():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='bedroom', name='Bedroom', count=3),
            RoomRequirement(type='living', name='Living room')
        ]
    )

    # "all bedrooms upstairs"
    intent = SpatialIntent(constraints=[
        SpatialConstraint(
            kind='floor_placement',
            priority='hard',
            source_text='All bedrooms upstairs',
            room=RoomReference(type='bedroom', target_all=True),
            floor=1
        )
    ])

    compiled = compile_intent(spec, intent)
    bedrooms = [r for r in compiled.specification.rooms if r.type == 'bedroom']

    assert len(bedrooms) == 3
    assert all(b.preferred_floor == 1 for b in bedrooms)
    assert next(r for r in compiled.specification.rooms if r.type == 'living').preferred_floor is None


def test_compile_architectural_layout_intent():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen')
        ]
    )

    intent = ArchitecturalLayoutIntent(
        room_categories={'living-1': RoomCategory.PUBLIC, 'kitchen-1': RoomCategory.SERVICE},
        room_enclosures={'living-1': RoomEnclosure.OPEN, 'dining-1': RoomEnclosure.OPEN},
        architectural_relationships=[
            RoomRelationship(
                source=RoomReference(type='living'),
                target=RoomReference(type='dining'),
                relation=ArchitecturalRelation.OPEN_TO,
                priority='hard'
            )
        ]
    )

    compiled = compile_intent(spec, intent)

    rooms_by_id = {r.name: r for r in compiled.specification.rooms}
    assert rooms_by_id['Living room'].category == RoomCategory.PUBLIC
    assert rooms_by_id['Living room'].enclosure == RoomEnclosure.OPEN
    assert rooms_by_id['Kitchen'].category == RoomCategory.SERVICE

    # Relationship converted to hard relationship constraint
    rel = next(r for r in compiled.specification.relationships if r.relation == ArchitecturalRelation.OPEN_TO)
    assert rel.source == 'living-1'
    assert rel.target == 'dining-1'


def test_backward_compatibility_with_existing_spec_and_spatial_intent():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='bedroom', name='Bedroom', count=2),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='dining', name='Dining')
        ],
        relationships=[
            Relationship(source='kitchen', target='dining', relation='connected')
        ]
    )

    compiled = compile_intent(spec, None)
    assert len(compiled.specification.rooms) == 4
    assert compiled.specification.spatial_intent is None

    # Relationship matches standard enum string
    assert compiled.specification.relationships[0].relation == ArchitecturalRelation.CONNECTED


# ============================================================================
# PHASE 2 TESTS: FUNCTIONAL ZONING & RELATIONSHIP-AWARE PLACEMENT
# ============================================================================

def test_phase2_public_rooms_prefer_public_zoning():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='bedroom', name='Master bedroom')
        ]
    )
    engine = DeterministicLayoutEngine()
    layout = engine.generate(spec)
    
    living = next(r for r in layout.rooms if r.type == 'living')
    dining = next(r for r in layout.rooms if r.type == 'dining')
    
    assert living.category == RoomCategory.PUBLIC
    assert dining.category == RoomCategory.PUBLIC
    # Public rooms placed in ground floor wing
    assert living.floor == 0
    assert dining.floor == 0
    assert living.wing_index == dining.wing_index


def test_phase2_private_rooms_prefer_private_zoning():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='bedroom', name='Master bedroom'),
            RoomRequirement(type='bedroom', name='Guest bedroom')
        ]
    )
    engine = DeterministicLayoutEngine()
    layout = engine.generate(spec)

    b1 = next(r for r in layout.rooms if r.name == 'Master bedroom')
    b2 = next(r for r in layout.rooms if r.name == 'Guest bedroom')

    assert b1.category == RoomCategory.PRIVATE
    assert b2.category == RoomCategory.PRIVATE
    # Default multi-floor private room placement prefers upper floors
    assert b1.floor == 1
    assert b2.floor == 1


def test_phase2_service_rooms_coherent():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='utility', name='Utility'),
            RoomRequirement(type='bathroom', name='Common Bath')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    kitchen = next(r for r in layout.rooms if r.type == 'kitchen')
    utility = next(r for r in layout.rooms if r.type == 'utility')
    bath = next(r for r in layout.rooms if r.type == 'bathroom')

    assert kitchen.category == RoomCategory.SERVICE
    assert utility.category == RoomCategory.SERVICE
    assert bath.category == RoomCategory.SERVICE


def test_phase2_open_to_adjacency():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen')
        ],
        relationships=[
            Relationship(source='living-1', target='dining-1', relation='open_to')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    living = next(r for r in layout.rooms if r.type == 'living')
    dining = next(r for r in layout.rooms if r.type == 'dining')

    # open_to forces same floor and same wing
    assert living.floor == dining.floor
    assert living.wing_index == dining.wing_index


def test_phase2_connected_dining_kitchen():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen')
        ],
        relationships=[
            Relationship(source='dining-1', target='kitchen-1', relation='connected')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    dining = next(r for r in layout.rooms if r.type == 'dining')
    kitchen = next(r for r in layout.rooms if r.type == 'kitchen')

    assert dining.floor == kitchen.floor
    assert dining.wing_index == kitchen.wing_index


def test_phase2_master_bedroom_attached_bathroom_adjacent():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='bedroom', name='Master bedroom', attached_bathroom=True),
            RoomRequirement(type='living', name='Living room')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    master = next(r for r in layout.rooms if r.name == 'Master bedroom')
    attached_bath = next(r for r in layout.rooms if r.attached_to == master.id)

    assert attached_bath is not None
    assert attached_bath.floor == master.floor
    assert attached_bath.wing_index == master.wing_index


def test_phase2_hard_floor_requirement_respected():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='bedroom', name='Ground Bedroom', preferred_floor=0),
            RoomRequirement(type='bedroom', name='Upper Bedroom', preferred_floor=1)
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    ground_bed = next(r for r in layout.rooms if r.name == 'Ground Bedroom')
    upper_bed = next(r for r in layout.rooms if r.name == 'Upper Bedroom')

    assert ground_bed.floor == 0
    assert upper_bed.floor == 1


def test_phase2_flexible_floor_rooms():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='bedroom', name='Flexible Bedroom 1'),
            RoomRequirement(type='bedroom', name='Flexible Bedroom 2')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    living = next(r for r in layout.rooms if r.type == 'living')
    b1 = next(r for r in layout.rooms if r.name == 'Flexible Bedroom 1')

    # Flexible public rooms go to ground floor 0, bedrooms to upper floor 1
    assert living.floor == 0
    assert b1.floor == 1


def test_phase2_away_from_preference():
    spec = HouseSpecification(
        plot_width=50, plot_length=70, floors=1,
        rooms=[
            RoomRequirement(type='bedroom', name='Bedroom'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='living', name='Living room')
        ],
        relationships=[
            Relationship(source='bedroom-1', target='kitchen-1', relation='away_from')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    bedroom = next(r for r in layout.rooms if r.type == 'bedroom')
    kitchen = next(r for r in layout.rooms if r.type == 'kitchen')

    assert bedroom.id is not None
    assert kitchen.id is not None


def test_phase2_impossible_hard_relationship_fails():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=2,
        rooms=[
            RoomRequirement(type='living', name='Living room', preferred_floor=0),
            RoomRequirement(type='bedroom', name='Upper Bedroom', preferred_floor=1)
        ],
        relationships=[
            Relationship(source='living-1', target='bedroom-1', relation='attached', priority='hard')
        ]
    )

    with pytest.raises(InfeasibleLayout):
        DeterministicLayoutEngine().generate(spec)


def test_phase2_baseline_cases_compatibility():
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='bedroom', name='Bedroom', count=2)
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)
    assert layout.candidate_count > 0
    assert len(layout.rooms) > 0


# ============================================================================
# PHASE 3 TESTS: PHYSICAL WALL TOPOLOGY & OPEN-SPACE RELATIONSHIPS
# ============================================================================

def test_phase3_open_to_suppresses_correct_shared_wall_geometry():
    """
    Test that open_to suppresses the exact shared boundary wall between living and dining
    while retaining exterior walls and unrelated walls, and leaving room geometries intact.
    """
    from shapely.geometry import Polygon, LineString

    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen')
        ],
        relationships=[
            Relationship(source='living-1', target='dining-1', relation='open_to')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    living = next(r for r in layout.rooms if r.type == 'living')
    dining = next(r for r in layout.rooms if r.type == 'dining')

    # Semantic rooms remain separate and intact
    assert living.id != dining.id
    assert living.width > 0 and living.height > 0
    assert dining.width > 0 and dining.height > 0

    living_poly = Polygon(living.polygon) if living.polygon else Polygon([(living.x, living.y), (living.x+living.width, living.y), (living.x+living.width, living.y+living.height), (living.x, living.y+living.height)])
    dining_poly = Polygon(dining.polygon) if dining.polygon else Polygon([(dining.x, dining.y), (dining.x+dining.width, dining.y), (dining.x+dining.width, dining.y+dining.height), (dining.x, dining.y+dining.height)])

    shared_boundary = living_poly.boundary.intersection(dining_poly.boundary)
    assert shared_boundary.length > 0.1, "Living and dining must share a physical boundary"

    # Verify no physical wall in layout.walls covers the shared boundary
    for w in layout.walls:
        w_line = LineString([(w.x1, w.y1), (w.x2, w.y2)])
        if not w.exterior:
            is_shared_wall = living_poly.boundary.buffer(1e-4).covers(w_line) and dining_poly.boundary.buffer(1e-4).covers(w_line)
            assert not is_shared_wall, f"Wall {w.id} along shared boundary was not suppressed!"

    # Verify exterior walls still exist and are untouched
    exterior_walls = [w for w in layout.walls if w.exterior]
    assert len(exterior_walls) > 0

    # Verify no interior swing door was created between living and dining across open boundary
    doors_between = [d for d in layout.doors if {d.room_a, d.room_b} == {living.id, dining.id}]
    assert len(doors_between) == 0, "No swing door should exist across an open_to boundary"


def test_phase3_enclosed_rooms_retain_separating_walls():
    """Test that enclosed rooms retain physical separating walls."""
    from shapely.geometry import Polygon, LineString

    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='bedroom', name='Bedroom 1'),
            RoomRequirement(type='bedroom', name='Bedroom 2'),
            RoomRequirement(type='living', name='Living room')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    b1 = next(r for r in layout.rooms if r.name == 'Bedroom 1')
    b2 = next(r for r in layout.rooms if r.name == 'Bedroom 2')

    b1_poly = Polygon(b1.polygon) if b1.polygon else Polygon([(b1.x, b1.y), (b1.x+b1.width, b1.y), (b1.x+b1.width, b1.y+b1.height), (b1.x, b1.y+b1.height)])
    b2_poly = Polygon(b2.polygon) if b2.polygon else Polygon([(b2.x, b2.y), (b2.x+b2.width, b2.y), (b2.x+b2.width, b2.y+b2.height), (b2.x, b2.y+b2.height)])

    shared_length = b1_poly.boundary.intersection(b2_poly.boundary).length
    if shared_length > 0.1:
        has_separating_wall = any(
            b1_poly.boundary.buffer(1e-4).covers(LineString([(w.x1, w.y1), (w.x2, w.y2)])) and
            b2_poly.boundary.buffer(1e-4).covers(LineString([(w.x1, w.y1), (w.x2, w.y2)]))
            for w in layout.walls if not w.exterior
        )
        assert has_separating_wall, "Enclosed bedrooms must retain their separating wall!"


def test_phase3_dining_kitchen_open_plan_geometry():
    """Test dining -> open_to -> kitchen produces valid open-plan topology."""
    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen')
        ],
        relationships=[
            Relationship(source='dining-1', target='kitchen-1', relation='open_to')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    dining = next(r for r in layout.rooms if r.type == 'dining')
    kitchen = next(r for r in layout.rooms if r.type == 'kitchen')

    # Both rooms remain independently identifiable
    assert dining.id != kitchen.id
    # No doors between open_to dining and kitchen
    doors_between = [d for d in layout.doors if {d.room_a, d.room_b} == {dining.id, kitchen.id}]
    assert len(doors_between) == 0


def test_phase3_wall_topology_integrity_no_zero_or_duplicate_walls():
    """Verify wall topology integrity: no zero length, no duplicates, valid wall IDs."""
    from math import hypot

    spec = HouseSpecification(
        plot_width=40, plot_length=60, floors=1,
        rooms=[
            RoomRequirement(type='living', name='Living room'),
            RoomRequirement(type='dining', name='Dining room'),
            RoomRequirement(type='kitchen', name='Kitchen'),
            RoomRequirement(type='bedroom', name='Bedroom')
        ],
        relationships=[
            Relationship(source='living-1', target='dining-1', relation='open_to')
        ]
    )
    layout = DeterministicLayoutEngine().generate(spec)

    wall_ids = [w.id for w in layout.walls]
    assert len(wall_ids) == len(set(wall_ids)), "Wall IDs must be unique"

    for w in layout.walls:
        length = hypot(w.x2 - w.x1, w.y2 - w.y1)
        assert length >= 0.001, f"Wall {w.id} has zero or near-zero length: {length}"

    assert not any(c.name == 'Valid building polygon' and c.status == 'ERROR' for c in layout.checks)


def test_phase_4_candidate_generation():
    """Test that the engine generates multiple structural candidates with varying strategies."""
    spec = HouseSpecification(
        width=40, length=60, floors=1, shape='rectangle', unit='feet',
        rooms=[
            RoomRequest(name='Living', type='living', minimum=150),
            RoomRequest(name='Dining', type='dining', minimum=100),
            RoomRequest(name='Kitchen', type='kitchen', minimum=100),
            RoomRequest(name='Bed1', type='bedroom', minimum=120),
            RoomRequest(name='Bath1', type='bathroom', minimum=40, bath=True),
        ]
    )
    
    engine = DeterministicLayoutEngine()
    layout = engine.generate(spec)
    
    assert layout.candidate_count >= 1
    assert len(layout.alternatives) > 0
    assert len(layout.alternatives) <= 5
    
    # Verify that the strategy was recorded
    for alt in layout.alternatives:
        assert hasattr(alt, 'strategy')
        
    assert layout.score is not None
    assert getattr(layout.score, 'strategy_score', None) is not None



