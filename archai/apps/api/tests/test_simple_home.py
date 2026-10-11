"""Functional circulation tests for the opt-in simple-home generator."""

from collections import Counter
from io import BytesIO

from PIL import Image

from app.exports import drawing_export, model_export
from app.layout import bounds, physically_open_pairs
from app.schemas import HouseShape, HouseSpecification
from app.simple_home import SimpleHomeLayoutEngine


def brief(bedrooms=2):
    return HouseSpecification.model_validate({
        'plot_width': 40, 'plot_length': 60, 'floors': 1,
        'shape': 'rectangle', 'road_location': 'north', 'parking_spaces': 1,
        'rooms': [
            {'type': 'bedroom', 'name': 'Bedroom', 'count': bedrooms},
            {'type': 'bathroom', 'name': 'Common bathroom', 'count': 2},
            {'type': 'living', 'name': 'Living room', 'count': 1},
            {'type': 'dining', 'name': 'Dining', 'count': 1},
            {'type': 'kitchen', 'name': 'Kitchen', 'count': 1},
            {'type': 'utility', 'name': 'Utility', 'count': 1},
        ],
        'relationships': [{'source': 'kitchen', 'target': 'dining', 'relation': 'connected'}],
    })


def test_simple_home_has_public_entry_open_kitchen_and_private_bath_access():
    spec = brief()
    layout = SimpleHomeLayoutEngine().generate(spec)
    assert layout.strategy == 'SIMPLE_HOME'
    assert not [check for check in layout.checks if check.status == 'ERROR']
    rooms = {room.id: room for room in layout.rooms}
    assert Counter(room.type for room in layout.rooms)['bedroom'] == 2
    assert any(door.room_a == 'porch-1' and door.room_b is None and door.kind == 'entry' for door in layout.doors)
    assert any(door.room_a == 'porch-1' and door.room_b == 'living-1' for door in layout.doors)
    assert not any(door.room_a == 'living-1' and door.room_b is None for door in layout.doors)
    assert any(door.room_a == 'parking-1' and door.room_b is None and door.kind == 'vehicle' for door in layout.doors)
    assert not any(door.room_a == 'parking-1' and door.room_b is not None for door in layout.doors)
    assert all(door.room_b == 'hall-0-0' for door in layout.doors if rooms[door.room_a].type in ('bedroom','bathroom'))
    assert {('dining-1','kitchen-1'),('dining-1','living-1')} <= physically_open_pairs(layout)
    assert not any({door.room_a,door.room_b} in ({'dining-1','kitchen-1'},{'dining-1','living-1'}) for door in layout.doors)
    assert bounds(rooms['living-1']).centroid.y < bounds(rooms['dining-1']).centroid.y
    assert layout.footprint.bounding_box[3] < layout.length  # rear yard remains


def test_three_bedroom_variant_preserves_every_requested_room():
    layout = SimpleHomeLayoutEngine().generate(brief(3))
    assert layout.strategy == 'SIMPLE_HOME'
    assert Counter(room.type for room in layout.rooms)['bedroom'] == 3
    assert not [check for check in layout.checks if check.status == 'ERROR']
    assert all(any(door.room_a == room.id and door.room_b == 'hall-0-0' for door in layout.doors)
               for room in layout.rooms if room.type == 'bedroom')


def test_exports_follow_the_same_open_wall_topology():
    layout = SimpleHomeLayoutEngine().generate(brief())
    png = Image.open(BytesIO(drawing_export(layout, 'png')[0]))
    # A point in the living/dining opening must not be painted as a wall.
    pixel = png.getpixel((int((23+2)*14), int((17+2)*14)))
    assert pixel != (38, 51, 74)
    assert drawing_export(layout, 'svg')[0].startswith(b'<svg')
    assert model_export(layout, 'glb')[0].startswith(b'glTF')


def test_unsupported_brief_retains_legacy_fallback():
    spec = brief()
    spec.shape = HouseShape.L_SHAPE
    assert not SimpleHomeLayoutEngine.supports(spec)
    fallback = SimpleHomeLayoutEngine().generate(spec)
    assert any(room.id == 'porch-1' for room in fallback.rooms)
    assert any(door.room_a == 'porch-1' and door.room_b == 'living-1' for door in fallback.doors)
    assert not [check for check in fallback.checks if check.status == 'ERROR']
