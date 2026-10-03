---
name: Nilam
description: A restrained Kerala land-intelligence workspace for spatial evidence and explainable model results.
colors:
  forest-ink: "#143f34"
  deep-ink: "#254f44"
  kerala-green: "#176149"
  evidence-green: "#29795f"
  constraint-rust: "#aa503d"
  muted-leaf: "#627870"
  warm-field: "#f5f3ed"
  paper: "#fffef9"
  divider: "#cdd9d3"
typography:
  display: "Libre Franklin 700"
  body: "DM Sans 400-700"
shape: "Square field-report panels; minimal rounding"
---

# Design System: Nilam

## Creative North Star: The Kerala Field Report

Nilam should feel like a careful field report placed beside a live map: calm,
legible, evidence-led, and specific to Kerala. Warm paper neutrals, restrained
greens, compact measurements, and square survey controls establish the visual
world. Color explains state and direction; it does not decorate empty space.

## Product Structure

Two equal workflow choices appear before the workspace:

- **Assess a site** supports Google place search, point selection, a drawn site
  boundary, normal/satellite maps, progressive model stages, Street View, and
  an exportable explanation.
- **Find matching land** supports a district, a drawn search boundary, or a
  25 km map-centred radius. It captures typed or spoken requirements, shows
  editable filters, and reports model suitability, preference fit, and combined
  rank separately.

The desktop workspace keeps the map and evidence panel together. Below 880px it
stacks in task order. A completed assessment scrolls the evidence panel into
view on small screens.

## Typography

- **Libre Franklin** carries the product promise, score, result title, and major
  editorial headings. Use tight tracking and strong weight.
- **DM Sans** carries controls, evidence, measurements, explanations, and
  metadata.
- Uppercase is reserved for eyebrows, statuses, and compact evidence labels.

## Color Rules

- Deep green structures the interface and marks confirmed or favourable state.
- Rust marks constraints, errors, and scientific cautions.
- Amber marks uncertain learned associations and evidence gaps.
- “Not mapped” must never be colored or described as proof of safety.

## Surface and Shape Rules

Analytical surfaces use one-pixel divider lines and tonal changes. The main
workspace, result panels, candidate rows, and controls stay square. Soft shadow
is reserved for the workspace container, map guidance, and dialogs that float
above another surface. Avoid decorative cards, glass effects, and pill-shaped
controls.

## Assessment Components

Lead with percentage, qualitative band, district, and a constraint-to-favourable
scale. The percentage is always called a model suitability index, never a safety
probability.

Show the TerraMind and TabPFN experts immediately after the result. Branch
scores and validation-calibrated fusion influence are distinct from SHAP feature
importance. During progressive analysis, pending branches say “Pending.”

SHAP drivers include a friendly label, observed value, and percentage-point
effect. Positive and negative effects occupy separate columns. Unmapped hazard
associations appear in a dedicated caution block and remain visible for audit.

## Candidate Components

The requirements composer leads the right panel. Exact distances are visible
and editable after Laya interpretation. Always-on hazard safeguards sit apart
from preferences. Candidate rows show three independent values: model
suitability, preference fit, and combined rank. A candidate is called a zone,
never a plot or available property, until authoritative parcel evidence exists.

## Interaction and Accessibility

- Every workflow, map style, and selection type has a visible selected state.
- Keyboard focus uses a three-pixel green outline with two-pixel offset.
- Loading is explained as mapped evidence, seasonal satellite analysis, and
  SHAP rather than a generic spinner.
- Rapid selections cancel stale browser requests.
- Motion respects `prefers-reduced-motion`.
- Street View is labeled as visual context and never feeds the suitability
  score.

## Scientific Copy Rules

State the weak-label limitation near research metrics. Keep on-site and legal
verification visible in completed reports. Do not describe model association as
causality, candidate rank as purchasability, land-cover class as confirmed
vacancy, or Google imagery as evidence of present-day site condition.
