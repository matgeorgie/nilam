---
name: Nilam
description: A restrained Kerala land-intelligence workspace for spatial evidence and explainable model results.
colors:
  forest-ink: "#153c32"
  deep-ink: "#0d2b24"
  kerala-green: "#17694f"
  evidence-green: "#258866"
  constraint-rust: "#b14f3c"
  muted-leaf: "#61766f"
  warm-field: "#f3f5f1"
  paper: "#ffffff"
  divider: "#d8e1dc"
typography:
  display: "Manrope 700-800"
  body: "DM Sans 400-700"
shape: "Restrained 8-20px rounding for controls, panels, and floating map results"
---

# Design System: Nilam

## Creative North Star: The Kerala Field Report

Nilam should feel like a careful field report placed beside a live map: calm,
legible, evidence-led, and specific to Kerala. Warm paper neutrals, restrained
greens, compact measurements, and square survey controls establish the visual
world. Color explains state and direction; it does not decorate empty space.

## Product Structure

Two permanent navigation choices keep the workflows separate:

- **Assess a site** supports Google place search, point selection, device
  location, a drawn site boundary, normal/satellite maps, an informative fusion wait state, nearby
  essentials, Street View, and a simple SHAP explanation.
- **Find suitable land** uses a clicked or searched centre and a 1–15 km
  radius. It captures typed or spoken requirements, shows Laya's interpretation,
  ranked result cards and sampled-cell footprints directly on the map. It first
  screens every generated cell for 45 m terrain flatness and recent open-ground
  evidence, then opens site details or camera-aligned nearby Street View when a
  result is selected.

The desktop workspace keeps the map and evidence panel together. Below 880px it
stacks in task order. A completed assessment scrolls the evidence panel into
view on small screens.

## Typography

- **Manrope** carries the product promise, score, result title, and major
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
workspace has a restrained 20-pixel radius; inputs and buttons use 8-11 pixels.
Soft shadow is reserved for the workspace container, map guidance, result
markers, and dialogs that float above another surface.

## Assessment Components

Lead with percentage, qualitative band, district, and a constraint-to-favourable
scale. The percentage is always called a model suitability index, never a safety
probability.

Show the TerraMind and TabPFN experts after the final result. Branch
scores and validation-calibrated fusion influence are distinct from SHAP feature
importance. During progressive analysis, show place-specific facts and model
activity without showing the mapped-data preview percentage.

SHAP drivers include a friendly label, observed value, and percentage-point
effect. Positive and negative effects use separate, plainly named lists.

## Candidate Components

Centre and radius selection lead the right panel, followed by optional text or
local voice preferences. Laya appears as a compact live activity, not a planner
form. Candidate map cards show combined match; the selected detail view separates
land suitability, open-land signal, and preference fit.

## Interaction and Accessibility

- Every workflow, map style, and selection type has a visible selected state.
- Keyboard focus uses a three-pixel green outline with two-pixel offset.
- Loading is explained as mapped data, satellite check, and explanation rather
  than a generic spinner.
- Rapid selections cancel stale browser requests.
- Motion respects `prefers-reduced-motion`.
- Street View is labeled as visual context and never feeds the suitability
  score.

## Scientific Copy Rules

State the weak-label limitation in academic documentation and research metrics,
outside the main decision flow. Do not describe model association as causality,
candidate rank as purchasability, land-cover class as confirmed vacancy, or
Google imagery as evidence of present-day site condition.
