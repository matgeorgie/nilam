# ArchAI: implementation, research and limits

## Decision for this laptop and deadline

Use local HouseGAN++ for 2D proposals and CubiCasa5K for uploaded floor-plan segmentation. Build 3D from one shared geometric layout. Improve the existing Three.js renderer rather than attempt a large new 3D foundation model in a one-day deadline on 8 GB RAM / GTX 1650 4 GB VRAM. Both inference paths were exercised on CPU, leaving GPU capacity for the browser.

The result is a functional prototype, not an architecturally validated reconstruction system or a photorealistic rendering product. The reference pictures require detailed assets, realistic surfaces, lighting and ray-traced rendering. Adding a neural mesh generator alone does not supply those or preserve the plan dimensions.

## Research comparisons (official sources)

| Approach | What it does | Fit here |
| --- | --- | --- |
| [HouseGAN++](https://github.com/ennauata/houseganpp) | Room layout generation conditioned on a room graph | Retained and repaired; does not create furnished 3D houses |
| [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k) | 44-channel floor-plan semantic prediction | Added genuine local checkpoint inference; contour conversion remains approximate |
| [FloorplanToBlender3d](https://github.com/grebtsew/FloorplanToBlender3d) | Image processing and procedural Blender conversion | Useful architectural pattern; not a pretrained 2D-to-photorealistic-3D model |
| [TripoSR](https://github.com/VAST-AI-Research/TripoSR) | Single-image object reconstruction | Official default about 6 GB VRAM; object images are different from architectural plans |
| [TRELLIS](https://github.com/microsoft/TRELLIS) | Generative 3D assets | Original implementation requires at least 16 GB VRAM; poor match to this laptop |
| [Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) | Shape and texture generation | Official requirements: 10 GB shape, 21 GB texture, 29 GB combined; unsuitable here |
| [Three.js MeshStandardMaterial](https://threejs.org/docs/pages/MeshStandardMaterial.html) | PBR rendering | Appropriate interactive scene renderer with textures, lighting and shadows |
| [Blender](https://www.blender.org/releases/4-5/) | Offline rendering | Optional later step for image quality; render script included but not verified |

No remote inference API was added. Models and material images are local after setup.

## Implemented pipeline

Text -> existing interpreter -> structured requirements -> HouseGAN++ candidate when eligible -> geometric validation -> accepted layout or deterministic fallback -> shared HouseLayout -> 2D drawing and 3D meshes.

Uploaded PNG/JPEG -> local CubiCasa5K model -> semantic room/wall/icon predictions -> contour and wall-span vectorisation -> draft HouseLayout -> 2D/3D viewer.

Imported JSON -> schema and geometry validation -> HouseLayout -> 3D. This route preserves the supplied geometry rather than predicting it. Canonical layout units are feet; GLB exports are scaled to metres.

### Model work

- Fixed HouseGAN room IDs, lower-left coordinates, class encoding and graph edges; removed unused torchvision imports.
- Cache the checkpoint and serialize inference; use CPU; test three seeded candidates.
- Validate learned candidates and explicitly record whether they were used. Current fixture falls back after invalid candidates. A loaded checkpoint is not evidence that its output was selected.
- Limit learned proposals to eligible single-floor simple plots. Existing planner handles unsupported constraints.
- Bundle the official CubiCasa checkpoint (~209 MB) and compatible upstream architecture. Tested actual output tensor of 44 channels. Attribution/license retained; CC BY-NC 4.0 applies.
- Uploaded image width sets scale. Margins count in this value; no automatic scale inference was implemented. Room labels/openings can be missed or wrong. Imported drafts must be reviewed.
- Natural-language parsing remains the original rule-based demo mode unless the existing optional provider is configured. This update does not add a local LLM or training pipeline.

### 3D and website work

- Full-height walls and a cutaway toggle, accurate door/window wall openings, improved framing.
- Detailed procedural beds, sofas, tables, chairs, wardrobes, kitchen units, fixtures, vehicles and plants.
- Local photographic wood/deck PBR maps, shadows, environment lighting and garden context. The terrain texture set is bundled but not currently applied.
- Working furniture toggle; import image/JSON modal; return from imported draft to saved project; layout JSON export.
- Furnished browser GLB export; backend geometry GLB export now preserves concave room polygons, diagonal walls and metric scale.
- Explicit AI status and reconstruction warnings. Image imports do not overwrite saved projects.

## Verification performed

- 4 focused backend tests passed: genuine HouseGAN checkpoint execution, polygon/diagonal-wall export and metre scale, controlled vectorisation, real CubiCasa image inference.
- 14 frontend unit tests passed; TypeScript typecheck passed.
- End-to-end browser test passed using installed Chrome: account/project creation, generation, 3D controls, furnished GLB download, JSON import, and no page errors.
- Real authenticated image endpoint returned 200 in about 1.9 seconds on the clean synthetic fixture (3 rooms, 12 wall spans). This is one example, not an accuracy evaluation. A colored plan image failed with no usable geometry, which demonstrates the input-style limitation.
- Screenshot reviewed. Interactive output is visibly more detailed but still below the supplied photorealistic references.
- Full legacy backend suite is NOT green. Existing backward-compatibility test expects four room requirement entries although the supplied spec has three entries with a bedroom count of two; seeded-demo test expects adjacency score 100 and gets 90. Related original planning/scoring source files were left unchanged. These failures need separate investigation before claiming complete regression coverage.
- No fresh-machine installation, production build, CUDA inference, architectural safety validation, or Blender render was verified. Setup/start/stop scripts have PowerShell syntax checks; the application was run with equivalent commands in this environment.

## Licensing and practical next work

Keep [CubiCasa attribution and CC BY-NC license](https://github.com/CubiCasa/CubiCasa5k), and review the included HouseGAN++ license before redistributing. Material maps are from [Poly Haven, CC0](https://polyhaven.com/license): wood_floor_deck, brown_planks_03, rocky_terrain_02. Furniture geometry is procedural, not downloaded proprietary assets.

For the one-day presentation, demonstrate the text/structured layout and exact JSON-to-3D path first, then clearly label image reconstruction experimental. Next priorities: collect representative plans and measure room/wall/door accuracy; add editable reconstruction correction; improve constraints for HouseGAN proposals; replace procedural furniture with curated licensed GLB assets; validate and tune Blender rendering. Do not advertise reference-level photorealism until that work is done.
