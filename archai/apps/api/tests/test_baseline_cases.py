"""Frozen Phase 3 observations; these test the legacy demo path, not LLM accuracy."""
import asyncio
import json
from collections import Counter
from pathlib import Path

import pytest

from app.ai.providers import MockAIProvider
from app.exports import drawing_export, model_export
from app.layout import DeterministicLayoutEngine, InfeasibleLayout, relationship_ok
from app.schemas import HouseSpecification


BASELINE = json.loads((Path(__file__).parent / 'fixtures' / 'baseline_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', BASELINE['cases'], ids=lambda case: case['id'])
def test_recorded_demo_baseline(case):
    spec = asyncio.run(MockAIProvider().extract(case['prompt'], HouseSpecification())).specification
    expected = case['extracted']
    if case['id'] == 'C7_master_explicit':
        master = next(room for room in spec.rooms if room.name == 'Master bedroom')
        assert master.minimum_area == expected['master_minimum_area']
        assert master.preferred_floor == expected['master_preferred_floor']
        assert [r.model_dump() for r in spec.relationships] == expected['relationships']
        assert spec.special_requirements == expected['special_requirements']
    else:
        for field in ('plot_width', 'plot_length', 'unit', 'floors', 'road_location', 'parking_spaces'):
            assert getattr(spec, field) == expected[field]
        assert spec.shape.value == expected['shape']
        assert list(spec.setbacks.model_dump().values()) == expected['setbacks']
        assert dict(Counter({kind: sum(r.count for r in spec.rooms if r.type == kind)
                             for kind in {r.type for r in spec.rooms}})) == expected['rooms']
        assert sum(r.count for r in spec.rooms if r.attached_bathroom) == expected['attached_bedrooms']
        assert [r.model_dump() for r in spec.relationships] == expected['relationships']
        if 'open_kitchen' in expected:
            assert spec.preferences.get('open_kitchen') == expected['open_kitchen']
        if 'bedroom_preferred_floors' in expected:
            assert [r.preferred_floor for r in spec.rooms if r.type == 'bedroom'] == expected['bedroom_preferred_floors']

    if 'failure' in case:
        with pytest.raises(InfeasibleLayout, match='This corridor layout requires') as failure:
            DeterministicLayoutEngine().generate(spec)
        assert str(failure.value) == case['failure']
        return

    layout = DeterministicLayoutEngine().generate(spec)
    result = case['result']
    assert layout.candidate_count == result['valid_candidates']
    if 'retained_alternatives' in result:
        assert len(layout.alternatives) == result['retained_alternatives']
        assert {c.name: c.status for c in layout.checks if c.name in BASELINE['passing_checks_for_generated_cases']} == {
            name: 'PASS' for name in BASELINE['passing_checks_for_generated_cases']
        }
        assert not [c for c in layout.checks if c.status == 'ERROR']
        if spec.parking_spaces:
            assert next(c.status for c in layout.checks if c.name == BASELINE['parking_check']) == 'PASS'
        assert dict(Counter(r.type for r in layout.rooms if r.type not in ('hall', 'stair') and not r.attached_to)) == result['rooms']
        assert [[r.id, r.floor] for r in layout.rooms if r.type == 'bedroom'] == result['bedroom_floors']
        assert [[r.id, round(r.width * r.height, 1)] for r in layout.rooms if r.type not in ('hall', 'stair')] == result['areas_ft2']
        assert [relationship_ok(layout, rel) for rel in spec.relationships] == result['relationships_met']
        assert len(drawing_export(layout, 'svg')[0]) == result['svg_export_bytes']
        assert len(model_export(layout, 'glb')[0]) == result['glb_export_bytes']
    else:
        master = next(r for r in layout.rooms if r.name == 'Master bedroom')
        assert master.floor == result['master_floor']
        assert round(master.width * master.height, 1) == result['master_area_ft2']
