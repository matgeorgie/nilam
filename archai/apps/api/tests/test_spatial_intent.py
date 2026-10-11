"""First AI increment: typed intent controls only deterministic candidate checks/ranking."""
import asyncio
import json
import os
import tempfile

# TestClient must never write to the developer's default apps/api/archai.db.
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + tempfile.mktemp(suffix='.db'))

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.intent import ClarificationNeeded, IntentError, compile_intent
from app.ai.providers import get_provider
from app.intent_validation import evaluate_intent
from app.layout import DeterministicLayoutEngine, InfeasibleLayout, relationship_ok, score
from app.main import app
from app.services import apply_operation
from app.schemas import (Extraction, HouseSpecification, Relationship, RoomReference,
                         RoomRequirement, SiteConstraints, SpatialConstraint, SpatialIntent, Operation,
                         UnsupportedRequest)


def spec():
    return HouseSpecification(plot_width=40, plot_length=60, floors=2, shape='rectangle',
        rooms=[RoomRequirement(type='bedroom', name='Master bedroom'),
               RoomRequirement(type='bedroom', name='Bedroom', count=2),
               RoomRequirement(type='kitchen', name='Kitchen'),
               RoomRequirement(type='dining', name='Dining'),
               RoomRequirement(type='living', name='Living room')])


def constraint(kind, **fields):
    return SpatialConstraint(kind=kind, priority='hard', source_text=kind, **fields)


def generate_with_intent(source, intent):
    compiled = compile_intent(source, intent)
    layout = DeterministicLayoutEngine().generate(compiled.specification,
        lambda candidate: evaluate_intent(candidate, compiled))
    return compiled, layout


def test_floor_placement_and_minimum_area_are_enforced():
    intent = SpatialIntent(constraints=[
        constraint('floor_placement', room=RoomReference(name='Master bedroom'), floor=0),
        constraint('minimum_area', room=RoomReference(name='Master bedroom'), area=200),
    ])
    compiled, layout = generate_with_intent(spec(), intent)
    master = next(room for room in layout.rooms if room.name == 'Master bedroom')
    assert master.floor == 0
    assert master.width * master.height >= 200
    assert next(room for room in compiled.specification.rooms if room.name == 'Master bedroom').minimum_area == 200
    assert all(check.status == 'PASS' for check in layout.checks if check.name.startswith('Spatial intent:'))


def test_setbacks_and_parking_road_access_are_independently_checked():
    source = spec()
    source.setbacks = SiteConstraints(front_setback=5, left_setback=3, right_setback=3)
    source.parking_spaces = 1
    source.road_location = 'south'
    intent = SpatialIntent(constraints=[
        constraint('setbacks', setbacks=source.setbacks),
        constraint('parking_access', road_side='south'),
    ])
    _, layout = generate_with_intent(source, intent)
    assert next(check.status for check in layout.checks if check.name == 'Setbacks respected') == 'PASS'
    assert next(check.status for check in layout.checks if check.name == 'Parking has road-reachable vehicle access') == 'PASS'
    assert all(check.status == 'PASS' for check in layout.checks if check.name.startswith('Spatial intent:'))
    source.road_location = 'north'
    with pytest.raises(IntentError, match='road side conflicts'):
        compile_intent(source, intent)


def test_unique_room_reference_and_kitchen_dining_connection():
    intent = SpatialIntent(constraints=[
        constraint('floor_placement', room=RoomReference(type='bedroom', ordinal=2), floor=1),
        constraint('relationship', room=RoomReference(type='kitchen'),
                   target=RoomReference(type='dining'), relation='connected'),
    ])
    compiled, layout = generate_with_intent(spec(), intent)
    assert next(room.floor for room in layout.rooms if room.id == 'bedroom-2') == 1
    assert relationship_ok(layout, Relationship(source='kitchen-1', target='dining-1', relation='connected'))
    assert len([check for check in layout.checks if check.name.startswith('Spatial intent:') and check.status == 'PASS']) == 2
    assert any(rel.source == 'kitchen-1' and rel.target == 'dining-1' for rel in compiled.specification.relationships)


def test_ambiguous_reference_is_not_guessed():
    intent = SpatialIntent(constraints=[constraint('floor_placement', room=RoomReference(type='bedroom'), floor=0)])
    with pytest.raises(ClarificationNeeded, match='ambiguous'):
        compile_intent(spec(), intent)


def test_unsupported_hard_request_is_rejected_not_downgraded():
    intent = SpatialIntent(unsupported_requests=[UnsupportedRequest(
        text='Guarantee compliance with every local building code', requested_priority='hard',
        reason='No jurisdiction-specific code validator exists.')])
    with pytest.raises(IntentError, match='Unsupported hard requirement'):
        compile_intent(spec(), intent)
    source = spec()
    source.special_requirements = ['Guarantee compliance with every local building code']
    with pytest.raises(IntentError, match='Unclassified special requirement'):
        compile_intent(source, SpatialIntent())


def test_contradictory_floor_and_setback_requirements_are_rejected():
    room = RoomReference(name='Master bedroom')
    intent = SpatialIntent(constraints=[constraint('floor_placement', room=room, floor=0),
                                        constraint('floor_placement', room=room, floor=1)])
    with pytest.raises(IntentError, match='Contradictory'):
        compile_intent(spec(), intent)
    intent = SpatialIntent(constraints=[constraint('setbacks', setbacks=SiteConstraints(front_setback=5))])
    with pytest.raises(IntentError, match='setback values conflict'):
        compile_intent(spec(), intent)


def test_no_valid_candidate_does_not_create_a_plan():
    intent = SpatialIntent(constraints=[constraint('minimum_area', room=RoomReference(name='Master bedroom'), area=10000)])
    with pytest.raises(InfeasibleLayout):
        generate_with_intent(spec(), intent)


def test_independent_check_rejects_a_corrupted_hard_floor_assignment():
    intent = SpatialIntent(constraints=[constraint('floor_placement',
        room=RoomReference(name='Master bedroom'), floor=0)])
    compiled, layout = generate_with_intent(spec(), intent)
    damaged = layout.model_copy(deep=True)
    next(room for room in damaged.rooms if room.name == 'Master bedroom').floor = 1
    checks, _ = evaluate_intent(damaged, compiled)
    assert checks[0].status == 'ERROR'


def test_soft_intent_changes_candidate_score_without_becoming_hard():
    intent = SpatialIntent(constraints=[SpatialConstraint(kind='relationship', priority='soft',
        source_text='prefer the kitchen near dining', room=RoomReference(type='kitchen'),
        target=RoomReference(type='dining'), relation='near')])
    compiled, layout = generate_with_intent(spec(), intent)
    assert layout.candidate_count > 0
    assert compiled.specification.relationships == []
    assert any(check.name.startswith('Spatial intent:') for check in layout.checks)
    _, bonus = evaluate_intent(layout, compiled)
    assert layout.score.overall_score == round(min(100, score(layout, compiled.specification).overall_score + bonus), 1)


def test_unsupported_soft_request_remains_explicit_warning():
    intent = SpatialIntent(unsupported_requests=[UnsupportedRequest(
        text='Prefer a solar-optimized roof', requested_priority='soft',
        reason='No roof optimization validator exists.')])
    _, layout = generate_with_intent(spec(), intent)
    assert any(c.name == 'Unsupported request: Prefer a solar-optimized roof' and
               c.status == 'WARNING' for c in layout.checks)


def test_malformed_model_data_is_rejected():
    with pytest.raises(ValidationError):
        Extraction.model_validate({'specification': spec().model_dump(), 'explanation': 'x',
                                   'spatial_intent': {'version': 1, 'constraints': [{'kind': 'floor_placement', 'priority': 'hard', 'source_text': 'upstairs', 'floor': 1}], 'unsupported_requests': []}})


def test_default_provider_is_local_even_with_old_environment(monkeypatch):
    from app.ai.local_model import LocalModelProvider
    monkeypatch.setenv('LLM_PROVIDER','openai')
    assert isinstance(get_provider(),LocalModelProvider)


def test_local_model_json_retry_rejects_wrong_ensuite_owner():
    from app.ai.local_model import LocalModelProvider,FloorDecision
    class FixtureModel:
        calls=0
        def create_chat_completion(self,**kwargs):
            self.calls+=1
            room={'type':'bathroom','name':'Shared bathroom','count':1,'preferred_floor':0,'attached_bathroom':self.calls==1}
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'rooms':[room],'questions':[]})}}]}
    fixture=FixtureModel();result=LocalModelProvider()._complete(fixture,[],FloorDecision.model_json_schema(),FloorDecision)
    assert fixture.calls==2 and not result.rooms[0].attached_bathroom


def test_lm_studio_provider_uses_configured_model(monkeypatch):
    import app.ai.local_model as local
    local.model.cache_clear()
    monkeypatch.setenv('ARCHAI_LM_STUDIO_MODEL','qwen/qwen3.5-9b')
    assert local.model().model_id=='qwen/qwen3.5-9b'
    local.model.cache_clear()


def test_edit_explicitly_reports_full_reflow_and_preserves_old_revision():
    with TestClient(app) as client:
        headers = {}
        original = client.post('/api/projects/demo', headers=headers).json()
        response = client.post(f"/api/projects/{original['id']}/chat",
                               json={'message': 'Make the master bedroom larger.'}, headers=headers)
        assert response.status_code == 200, response.text
        assert 'regenerated the whole plan' in response.json()['reply']
        assert response.json()['project']['current_revision'] != original['current_revision']
        old = client.get(f"/api/projects/{original['id']}/revisions", headers=headers).json()
        assert any(item['id'] == original['current_revision'] for item in old)


def test_edit_retains_prior_hard_intent_during_regeneration():
    intent = SpatialIntent(constraints=[constraint('floor_placement',
        room=RoomReference(name='Master bedroom'), floor=0)])
    compiled, before = generate_with_intent(spec(), intent)
    operation = Operation(operation='resize_room', target_room='Master bedroom', parameters={'factor': 1.2})
    changed_spec = apply_operation(compiled.specification, operation, before)
    assert changed_spec.spatial_intent == intent
    _, after = generate_with_intent(changed_spec, intent)
    assert next(room.floor for room in after.rooms if room.name == 'Master bedroom') == 0
    assert next(room.floor for room in before.rooms if room.name == 'Master bedroom') == 0
