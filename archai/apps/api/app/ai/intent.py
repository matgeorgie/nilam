"""Resolve coordinate-free spatial intent against concrete room instances."""
from dataclasses import dataclass

from ..schemas import (ArchitecturalLayoutIntent, HouseSpecification, Relationship,
                        RoomCategory, RoomEnclosure, RoomReference, SpatialConstraint, SpatialIntent,
                        default_room_category)


class IntentError(ValueError):
    pass


class ClarificationNeeded(IntentError):
    pass


@dataclass(frozen=True)
class ResolvedConstraint:
    request: SpatialConstraint
    room_id: str | None = None
    target_id: str | None = None


@dataclass
class CompiledIntent:
    specification: HouseSpecification
    constraints: list[ResolvedConstraint]


def _expand_rooms(specification):
    """Mirror the generator's type counters, names, and IDs without geometry."""
    counters = {}
    expanded = []
    for requirement in specification.rooms:
        for _ in range(requirement.count):
            ordinal = counters.get(requirement.type, 0) + 1
            counters[requirement.type] = ordinal
            room = requirement.model_copy(deep=True)
            room.count = 1
            room.name = requirement.name if requirement.count == 1 else f'{requirement.name} {ordinal}'
            expanded.append((f'{requirement.type}-{ordinal}', ordinal, requirement.name, room))
    return expanded


def _resolve_rooms(reference: RoomReference, rooms):
    matches = rooms
    if reference.type:
        matches = [item for item in matches if item[3].type.casefold() == reference.type.casefold()]
    if reference.name:
        matches = [item for item in matches if reference.name.casefold() in
                   (item[0].casefold(), item[2].casefold(), item[3].name.casefold())]
    if reference.ordinal is not None:
        matches = [item for item in matches if item[1] == reference.ordinal]
    return matches


def _resolve(reference: RoomReference, rooms):
    matches = _resolve_rooms(reference, rooms)
    if reference.target_all:
        if not matches:
            raise ClarificationNeeded(f'The room reference {reference.model_dump(exclude_none=True)} is unknown; identify at least one room.')
        return matches
    if len(matches) != 1:
        problem = 'ambiguous' if matches else 'unknown'
        raise ClarificationNeeded(f'The room reference {reference.model_dump(exclude_none=True)} is {problem}; identify exactly one room.')
    return [matches[0]]


def compile_intent(specification: HouseSpecification, intent: SpatialIntent | None) -> CompiledIntent:
    spec = specification.model_copy(deep=True)
    if intent is None:
        return CompiledIntent(spec, [])
    for text in spec.special_requirements:
        if not any(request.text.casefold() == text.casefold() for request in intent.unsupported_requests):
            raise IntentError(f'Unclassified special requirement: {text}. Mark it explicitly unsupported before generating.')
    for request in intent.unsupported_requests:
        if request.requested_priority == 'hard':
            raise IntentError(f'Unsupported hard requirement: {request.text}. {request.reason}')
    
    # Process architectural relationships into spatial constraints if present
    if hasattr(intent, 'architectural_relationships') and intent.architectural_relationships:
        for arch_rel in intent.architectural_relationships:
            sc = SpatialConstraint(
                kind='relationship',
                priority=arch_rel.priority,
                source_text=f"{arch_rel.source.type or arch_rel.source.name} {arch_rel.relation.value} {arch_rel.target.type or arch_rel.target.name}",
                room=arch_rel.source,
                target=arch_rel.target,
                relation=arch_rel.relation
            )
            if not any(c.room == sc.room and c.target == sc.target and c.relation == sc.relation for c in intent.constraints):
                intent.constraints.append(sc)

    rooms = _expand_rooms(spec)
    
    # Attach category and enclosure to each room requirement instance
    for room_id, _, _, req in rooms:
        cat = intent.room_categories.get(room_id) or req.category or default_room_category(req.type)
        enc = intent.room_enclosures.get(room_id) or req.enclosure or RoomEnclosure.ENCLOSED
        req.category = cat
        req.enclosure = enc

    resolved = []
    hard_floors = {}
    for constraint in intent.constraints:
        matched_rooms = _resolve(constraint.room, rooms) if constraint.room else [None]
        matched_targets = _resolve(constraint.target, rooms) if constraint.target else [None]
        
        for room in matched_rooms:
            for target in matched_targets:
                room_id = room[0] if room else None
                target_id = target[0] if target else None
                if room_id and room_id == target_id:
                    raise IntentError('A room cannot have a spatial relationship with itself.')
                if constraint.kind == 'floor_placement':
                    if spec.floors is not None and constraint.floor >= spec.floors:
                        raise IntentError(f'Floor {constraint.floor} does not exist in this house.')
                    if constraint.priority == 'hard' and room:
                        previous = hard_floors.get(room_id)
                        if previous is not None and previous != constraint.floor:
                            raise IntentError(f'Contradictory floor requirements for {room[3].name}.')
                        hard_floors[room_id] = constraint.floor
                        if room[3].preferred_floor is not None and room[3].preferred_floor != constraint.floor:
                            raise IntentError(f'Conflicting floor requirements for {room[3].name}.')
                        room[3].preferred_floor = constraint.floor
                elif constraint.kind == 'minimum_area' and room:
                    if constraint.priority == 'hard':
                        room[3].minimum_area = max(room[3].minimum_area or 0, constraint.area)
                elif constraint.kind == 'relationship':
                    if constraint.priority == 'hard' and room_id and target_id:
                        relation = Relationship(source=room_id, target=target_id, relation=constraint.relation)
                        if relation not in spec.relationships:
                            spec.relationships.append(relation)
                elif constraint.kind == 'setbacks':
                    if spec.setbacks != constraint.setbacks:
                        raise IntentError('The extracted setback values conflict with the spatial intent; please clarify.')
                elif constraint.kind == 'parking_access':
                    if not spec.parking_spaces:
                        raise IntentError('Vehicle access was requested without a parking space.')
                    if spec.road_location != constraint.road_side:
                        raise IntentError('The extracted road side conflicts with the spatial intent; please clarify.')
                resolved.append(ResolvedConstraint(constraint, room_id, target_id))

    spec.rooms = [item[3] for item in rooms]
    spec.spatial_intent = intent
    return CompiledIntent(HouseSpecification.model_validate(spec.model_dump()), resolved)
