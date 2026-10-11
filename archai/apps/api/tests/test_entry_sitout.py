"""The application-facing generator must not omit the entry transition."""

import pytest

from app.layout import validate
from app.ml.engine import MLGenerativeLayoutEngine
from app.schemas import HouseSpecification
from app.simple_home import SimpleHomeLayoutEngine


def fallback_brief(side, parking):
    return HouseSpecification.model_validate({
        'plot_width': 40, 'plot_length': 60, 'floors': 2,
        'shape': 'rectangle', 'road_location': side, 'parking_spaces': parking,
        'rooms': [
            {'type': 'bedroom', 'name': 'Bedroom', 'count': 2},
            {'type': 'bathroom', 'name': 'Bathroom'},
            {'type': 'living', 'name': 'Living room'},
            {'type': 'dining', 'name': 'Dining'},
            {'type': 'kitchen', 'name': 'Kitchen'},
        ],
    })


@pytest.mark.parametrize('side', ['north', 'south', 'east', 'west'])
@pytest.mark.parametrize('parking', [0, 1])
def test_all_road_sides_have_a_sitout_before_living(side, parking):
    spec = fallback_brief(side, parking)
    layout = SimpleHomeLayoutEngine().generate(spec)
    porch = next(room for room in layout.rooms if room.id == 'porch-1')
    assert porch.floor == 0 and porch.type == 'porch'
    assert porch.width * porch.height >= 50
    assert any(door.room_a == porch.id and door.room_b is None and door.kind == 'entry'
               for door in layout.doors)
    assert any(door.room_a == porch.id and door.room_b and
               next(room for room in layout.rooms if room.id == door.room_b).type == 'living'
               for door in layout.doors)
    assert not any(door.room_a == 'living-1' and door.room_b is None for door in layout.doors)
    assert not [check for check in validate(layout, spec) if check.status == 'ERROR']
    if parking:
        assert not any(door.room_a == 'parking-1' and door.room_b for door in layout.doors)


def test_removed_sitout_connection_is_a_hard_validation_error():
    spec = fallback_brief('south', 0)
    layout = SimpleHomeLayoutEngine().generate(spec)
    layout.doors = [door for door in layout.doors
                    if not (door.room_a == 'porch-1' and door.room_b == 'living-1')]
    check = next(check for check in validate(layout, spec)
                 if check.name == 'Road to sit-out to living route')
    assert check.status == 'ERROR'


def test_existing_south_road_auto_shape_brief_gets_sitout():
    spec = HouseSpecification.model_validate({
        'plot_width': 30, 'plot_length': 50, 'floors': 2,
        'shape': 'auto', 'road_location': 'south',
        'rooms': [
            {'type': 'bedroom', 'name': 'Master bedroom'},
            {'type': 'bedroom', 'name': 'Bedroom 2'},
            {'type': 'bathroom', 'name': 'Common bathroom'},
            {'type': 'kitchen', 'name': 'Kitchen'},
            {'type': 'dining', 'name': 'Dining'},
            {'type': 'living', 'name': 'Living room'},
        ],
        'relationships': [{'source': 'kitchen', 'target': 'dining', 'relation': 'connected'}],
    })
    layout = SimpleHomeLayoutEngine().generate(spec)
    assert any(room.id == 'porch-1' for room in layout.rooms)
    assert not [check for check in validate(layout, spec) if check.status == 'ERROR']


@pytest.mark.parametrize('weights_loaded', [False, True])
def test_active_ml_adapter_cannot_bypass_sitout_validation(weights_loaded):
    spec = fallback_brief('south', 0)
    engine = MLGenerativeLayoutEngine(model_path=None)
    engine.is_loaded = weights_loaded
    layout = engine.generate(spec)
    assert any(room.id == 'porch-1' for room in layout.rooms)
    assert not [check for check in validate(layout, spec) if check.status == 'ERROR']


def test_stair_location_follows_road_side_and_has_no_cross_wall():
    positions = {}
    for side in ('north', 'south'):
        spec = fallback_brief(side, 0)
        layout = SimpleHomeLayoutEngine().generate(spec)
        stair = layout.stairs[0]
        positions[side] = stair.y
        assert all(other.x == stair.x and other.y == stair.y
                   for other in layout.stairs)
        hall = next(room for room in layout.rooms if room.id == 'hall-0-0')
        approach = stair.y + stair.length if abs(stair.y - hall.y) < .01 else stair.y
        assert not any(wall.floor == 0 and abs(wall.y1 - approach) < .01
                       and abs(wall.y2 - approach) < .01
                       and wall.x1 <= stair.x + .01
                       and wall.x2 >= stair.x + stair.width - .01
                       for wall in layout.walls)
        assert not [check for check in validate(layout, spec) if check.status == 'ERROR']
    assert positions['north'] != positions['south']


def test_pretrained_housegan_prior_only_ranks_valid_single_floor_candidates():
    spec = fallback_brief('south', 0)
    spec.floors = 1
    engine = MLGenerativeLayoutEngine()
    assert engine.is_loaded
    layout = engine.generate(spec)
    assert any(check.name == 'HouseGAN++ candidate prior' for check in layout.checks)
    assert any(room.id == 'porch-1' for room in layout.rooms)
    assert not [check for check in validate(layout, spec) if check.status == 'ERROR']
