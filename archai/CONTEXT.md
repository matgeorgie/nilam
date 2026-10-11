# Constrained Generative Architecture

ArchAI turns residential requirements into measurable conceptual plans while keeping computational validity distinct from professional approval.

## Language

**House Specification**:
The structured statement of site, room, relationship, accessibility, orientation, and preference requirements supplied by or confirmed with a user.
_Avoid_: Prompt, brief JSON

**Spatial Intent**:
The user's stated or inferred spatial priorities for specific rooms and site relationships, separated from coordinates and classified as hard or soft only when their meaning can be checked.
_Avoid_: Floor plan, model geometry

**Resolved Room Reference**:
A reference that identifies exactly one room instance within a House Specification.
_Avoid_: Room type, guessed room

**Unsupported Hard Request**:
A user-mandatory condition for which the system has no corresponding validity check; it cannot be silently accepted or treated as a preference.
_Avoid_: Soft constraint, warning-only requirement

**Plot**:
The legally or operationally available parcel boundary, road relationship, and north reference within which a design is considered.
_Avoid_: Canvas, page

**Buildable Area**:
The portion of a plot remaining after the declared setback rules are applied.
_Avoid_: House outline

**Building Footprint**:
The exterior building polygon, optionally containing interior voids such as a courtyard, that must lie inside the buildable area.
_Avoid_: Template, room box

**Room**:
A named semantic space with polygonal geometry, minimum and preferred qualities, access, privacy, openings, and relationships.
_Avoid_: Node, rectangle

**Vehicle Bay**:
A ground-floor space sized for one vehicle, with a vehicle-width exterior opening and an unobstructed route across the plot to the declared road edge. It may also have a separate pedestrian connection to the house.
_Avoid_: Parking room, ordinary room with a car symbol

**Vehicle Gate**:
An exterior wall opening wide enough for vehicle movement that connects a Vehicle Bay toward the road; it is distinct from a pedestrian door.
_Avoid_: Door, entrance door

**Candidate Plan**:
A complete structured plan proposed for one House Specification and independently validated before ranking.
_Avoid_: Image option, random result

**Hard Constraint**:
A condition whose failure makes a Candidate Plan computationally invalid.
_Avoid_: Penalty, preference

**Soft Constraint**:
A desirable condition that contributes to ranking without invalidating a Candidate Plan.
_Avoid_: Rule, guarantee

**Computational Validity**:
Passing the declared geometric and architectural checks implemented by the system.
_Avoid_: Code compliance, construction-ready, architect-approved

**Plan Revision**:
An immutable saved pairing of a House Specification and its selected Candidate Plan.
_Avoid_: Save, autosave snapshot
