"""Regression checks for the living-first two-storey courtyard brief."""

from collections import Counter
from io import BytesIO
import asyncio

from PIL import Image
import pytest

from app.courtyard_home import CourtyardHomeLayoutEngine
from app.ai.providers import MockAIProvider
from app.exports import drawing_export, model_export
from app.layout import InfeasibleLayout, physically_open_pairs, validate
from app.schemas import HouseShape, HouseSpecification
from app.simple_home import SimpleHomeLayoutEngine


def courtyard_brief():
    return HouseSpecification.model_validate({
        'plot_width': 40, 'plot_length': 60, 'floors': 2,
        'shape': 'courtyard', 'road_location': 'north', 'parking_spaces': 1,
        'rooms': [
            {'type': 'bedroom', 'name': 'Master bedroom', 'count': 1,
             'minimum_area': 216.72, 'attached_bathroom': True},
            {'type': 'bathroom', 'name': 'Common bathroom', 'count': 1},
            {'type': 'living', 'name': 'Living room', 'count': 1},
            {'type': 'dining', 'name': 'Dining', 'count': 1},
            {'type': 'kitchen', 'name': 'Kitchen', 'count': 1},
            {'type': 'utility', 'name': 'Utility', 'count': 1},
        ],
        'relationships': [{'source': 'kitchen', 'target': 'dining', 'relation': 'connected'}],
    })


def test_courtyard_arrival_is_living_before_dining_and_kitchen():
    spec = courtyard_brief()
    assert CourtyardHomeLayoutEngine.supports(spec)
    layout = SimpleHomeLayoutEngine().generate(spec)
    assert layout.strategy == 'COURTYARD_HOME'
    assert not [check for check in validate(layout, spec) if check.status == 'ERROR']
    rooms = {room.id: room for room in layout.rooms}
    assert {rooms[room_id].floor for room_id in ('living-1', 'dining-1', 'kitchen-1')} == {0}
    assert rooms['bedroom-1'].floor == 1
    assert Counter(room.type for room in layout.rooms)['bedroom'] == 1
    assert any(door.room_a == 'porch-1' and door.room_b is None and door.kind == 'entry'
               for door in layout.doors)
    assert any(door.room_a == 'porch-1' and door.room_b == 'living-1' for door in layout.doors)
    assert not any(door.room_a == 'dining-1' and door.room_b is None for door in layout.doors)
    assert any({door.room_a, door.room_b} == {'living-1', 'hall-0-0'} for door in layout.doors)
    assert any({door.room_a, door.room_b} == {'dining-1', 'hall-0-0'} for door in layout.doors)
    assert ('dining-1', 'kitchen-1') in physically_open_pairs(layout)
    assert not any({door.room_a, door.room_b} == {'dining-1', 'kitchen-1'} for door in layout.doors)
    assert any({door.room_a, door.room_b} == {'kitchen-1', 'utility-1'} for door in layout.doors)
    assert any({door.room_a, door.room_b} == {'bathroom-1', 'hall-0-1'} for door in layout.doors)
    assert not any(door.room_a == 'parking-1' and door.room_b for door in layout.doors)
    assert rooms['parking-1'].height >= 18


def test_courtyard_does_not_hide_infeasible_area():
    spec = courtyard_brief()
    next(room for room in spec.rooms if room.type == 'dining').minimum_area = 500
    with pytest.raises(InfeasibleLayout, match='Dining cannot meet'):
        SimpleHomeLayoutEngine().generate(spec)


def test_courtyard_exports_2d_and_3d():
    layout = SimpleHomeLayoutEngine().generate(courtyard_brief())
    image = Image.open(BytesIO(drawing_export(layout, 'png')[0]))
    assert image.width > 0 and image.height > 0
    assert drawing_export(layout, 'svg')[0].startswith(b'<svg')
    assert model_export(layout, 'glb')[0].startswith(b'glTF')


def test_explicit_two_floor_brief_keeps_all_rooms_and_living_first():
    prompt = (
        'Design a modern two-story house on a 40 × 60 ft plot with a road on the north side. '
        'Include an open car porch at the front with direct driveway access. '
        'On the ground floor, place a welcoming living room near the entrance, a dining area connected '
        'to the kitchen, one bedroom with an attached bathroom, a common bathroom, and a utility area. '
        'Upstairs, include three bedrooms, two bathrooms, and a small family lounge.'
    )
    spec = asyncio.run(MockAIProvider().extract(prompt, HouseSpecification())).specification
    spec.shape = HouseShape.COURTYARD
    assert Counter({kind: sum(room.count for room in spec.rooms if room.type == kind)
                    for kind in ('bedroom', 'bathroom', 'living')}) == {
                        'bedroom': 4, 'bathroom': 3, 'living': 2,
                    }
    assert CourtyardHomeLayoutEngine.supports(spec)
    layout = SimpleHomeLayoutEngine().generate(spec)
    assert layout.strategy == 'COURTYARD_HOME'
    assert not [check for check in validate(layout, spec) if check.status == 'ERROR']
    assert Counter(room.type for room in layout.rooms)['bedroom'] == 4
    assert Counter(room.type for room in layout.rooms)['bathroom'] == 4  # 3 common + attached
    assert [room.floor for room in layout.rooms if room.type == 'bedroom'].count(1) == 3
    assert any(room.name == 'Family lounge' and room.floor == 1 for room in layout.rooms)
    assert ('dining-1', 'kitchen-1') in physically_open_pairs(layout)
    assert any(door.room_a == 'porch-1' and door.room_b is None and door.kind == 'entry'
               for door in layout.doors)
    assert any(door.room_a == 'porch-1' and door.room_b == 'living-1' for door in layout.doors)
    assert drawing_export(layout, 'svg')[0].startswith(b'<svg')
    assert model_export(layout, 'glb')[0].startswith(b'glTF')
