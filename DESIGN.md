---
name: Nilam
description: A restrained Kerala land-intelligence workspace for spatial evidence and explainable model results.
colors:
  forest-ink: "#123c31"
  deep-ink: "#16392f"
  kerala-green: "#176149"
  evidence-green: "#2c8063"
  constraint-rust: "#a3523e"
  muted-leaf: "#60736b"
  warm-field: "#f3f5f0"
  paper: "#fbfcf9"
  divider: "#d5ddd7"
  sand: "#f0ede3"
typography:
  display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "58px"
    fontWeight: 500
    lineHeight: 0.94
    letterSpacing: "-0.035em"
  title:
    fontFamily: "DM Sans, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: "DM Sans, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "DM Sans, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  control: "5px"
  group: "8px"
  floating: "10px"
  dialog: "14px"
spacing:
  xs: "5px"
  sm: "10px"
  md: "18px"
  lg: "24px"
  xl: "38px"
components:
  segmented-selected:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
  map-prompt:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.floating}"
    padding: "13px 16px"
  score-panel:
    backgroundColor: "#edf3ed"
    textColor: "{colors.forest-ink}"
    padding: "24px 22px 17px"
---

# Design System: Nilam

## Overview

**Creative North Star: "The Kerala Field Report"**

Nilam feels like a careful field report placed beside a live map: calm, legible, evidence-led, and specific to Kerala. The interface uses warm paper neutrals, restrained greens, and compact analytical detail. Editorial display type gives the research work a human voice while conventional controls keep the spatial task familiar.

The map and report are equal working surfaces on desktop. On mobile, selection comes first and a completed analysis moves directly to the score. Color explains state and effect; it does not decorate empty space.

**Key Characteristics:**
- Warm paper field with deep Kerala-green structure.
- Large editorial headings paired with compact sans-serif evidence.
- Flat bordered surfaces with depth reserved for floating map controls.
- Suitability score followed by signed, value-bearing SHAP drivers.

## Colors

The palette is quiet and botanical, with rust reserved for model constraints.

### Primary
- **Kerala Green:** Primary actions, selected map controls, score support, and favourable effects.
- **Forest Ink:** Main text, headings, and structural emphasis.

### Secondary
- **Constraint Rust:** Limiting SHAP effects and low-suitability states only.

### Neutral
- **Warm Field:** Page ground.
- **Paper:** Main workspace and elevated control surfaces.
- **Muted Leaf:** Supporting copy and metadata.
- **Divider:** Fine boundaries between evidence rows and work areas.

### Named Rules

**The Evidence Color Rule.** Green and rust must encode direction or state; neither is ambient decoration.

## Typography

**Display Font:** Newsreader (with Georgia fallback)  
**Body Font:** DM Sans (with Arial fallback)

**Character:** Newsreader gives major headings the measured tone of an environmental report. DM Sans keeps map controls, measurements, and explanations compact and clear.

### Hierarchy
- **Display** (500, 58px desktop / 43px mobile, 0.94): Product promise and major empty-state headings.
- **Title** (600, 20px, 1.2): District and result titles.
- **Body** (400, 13px, 1.65): Explanations and research context.
- **Label** (600, 11px): Controls, evidence metadata, and factor values; uppercase is reserved for compact statuses.

### Named Rules

**The Two-Voice Rule.** Newsreader speaks only for major editorial headings; all task controls and evidence stay in DM Sans.

## Layout

The core workspace is a bordered two-column grid: the map receives roughly three-fifths of the width and the report receives the remainder. Toolbars are 62px high. Evidence rows use a compact 10–24px spacing rhythm. At 780px and below, the workspace stacks; map tools become a small grid and completed analysis scrolls the report score into view. At 1100px and below, the desktop columns tighten without changing the task order.

## Elevation & Depth

The system is flat by default. Borders and tonal changes separate the workspace, score, evidence, and research sections. A single soft shadow is allowed for floating map prompts and selected segmented controls; dialogs use a wider ambient shadow because they temporarily leave the page plane.

### Shadow Vocabulary
- **Floating Map Prompt** (`0 6px 24px #143b2c24`): Guidance positioned over the map.
- **Selected Control** (`0 1px 4px #173c2d1a`): Active option inside a segmented control.
- **Dialog** (`0 25px 90px #0d2b214d`): Research-method dialog only.

**The Flat Workspace Rule.** Analytical surfaces use borders and tone; shadows belong only to elements that physically float over another task surface.

## Shapes

Controls use gently rounded corners: 5px within segmented groups, 8px for groups and error actions, 10px for floating map guidance, and 14px for the dialog. Evidence panels remain rectangular and rely on shared borders. Pills and exaggerated rounding are outside the system.

## Components

### Buttons
- **Shape:** Compact control corners (5–8px) with 7px 10px internal padding.
- **Selected:** Paper background, forest text, and a low selected-control shadow.
- **Focus:** A 3px amber outline with 2px offset.
- **Clear / recovery:** Text-level rust for clearing; solid forest for recovery actions.

### Cards / Containers
- **Corner Style:** The workspace and report panels remain square; only floating guidance uses a 10px radius.
- **Background:** Paper for task surfaces and pale green for score results.
- **Shadow Strategy:** Flat except for true overlays.
- **Border:** One-pixel divider lines.

### Inputs / Fields
- Native selects retain familiar browser behavior, use transparent backgrounds, and carry forest text. Group labels are compact and uppercase only where they identify a control category.

### Navigation
- The masthead uses the lowercase Nilam wordmark at left and an underlined research-method action at right. Map modes and styles use segmented buttons with visible selected state and `aria-pressed` semantics.

### Suitability Result
- Lead with the percentage, qualitative band, district, and a constraint-to-favourable scale.
- List SHAP drivers in supported and reduced columns with the actual feature value and percentage-point effect.
- Aggregate the same effects into semantic evidence groups below the factor list.

### Multimodal Fusion Trace
- Place the fusion trace directly after the suitability result so users can see how the score was assembled before reading individual SHAP drivers.
- Show satellite seasons, mapped site evidence, and cross-attention as three parallel streams with their branch estimate and learned routing weight.
- Use the active green status only when the multimodal artifact produced the current result.
- State that routing weights describe model combination, not causal feature importance.

## Do's and Don'ts

### Do:
- **Do** keep the map and explanation visible together on desktop.
- **Do** pair each model effect with a friendly feature name, measured value, direction, and percentage-point contribution.
- **Do** preserve an explicit weak-label and non-certification statement near research claims.
- **Do** clear stale results when the user changes the model.

### Don't:
- **Don't** use green or rust without a state or directional meaning.
- **Don't** present class confidence as construction-safety probability.
- **Don't** add hazard overlays to the primary map workspace.
- **Don't** hide missing model output behind an incomplete evidence report; use a clear unavailable state and recovery action.
