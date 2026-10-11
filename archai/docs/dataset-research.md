# Dataset and model research

Research performed 20 September 2026. “Usable” below is a product-policy recommendation, not legal advice; preserve attribution and have counsel review dataset provenance before commercial training.

## Dataset comparison

| Dataset | Scale and domain | Representation and labels | Walls / openings / dimensions / site | Published terms | Decision |
|---|---|---|---|---|---|
| [RPLAN](https://ustc-gcl-f.github.io/projects/DeepLayout/index.html) | 80,788 real residential plans | Four-channel 256×256 raster; room types and instances | Encodes boundary, walls and doors; no reliable metric dimensions, plot, road, or setbacks | A clear redistribution/commercial license was not found on the official project page | Do not download or train until written terms are verified; useful only as a research benchmark reference |
| [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k) | 5,000 real residential floor plans; 80+ categories | Raster source plus dense SVG polygon annotations and room/object labels | Walls, doors, windows and fixtures; scale/dimensions and parcel boundary are not consistently available | CC BY-NC 4.0 data; repository code has its own license | Research/non-commercial parsing and vectorization experiments only; not a production-training default |
| [Structured3D](https://structured3d-dataset.org/) | 3,500 professionally designed synthetic houses | Rich 3D structure, semantics, panorama and rendered imagery | Structural lines, rooms and 3D geometry; not a cadastral plot/road dataset | Dataset-specific Terms of Use and agreement; code MIT | Useful for 2D↔3D reconstruction research after accepting terms, not the first residential layout-generation corpus |
| [HouseExpo](https://github.com/TeaganLi/HouseExpo) | 35,126 indoor layouts and 252,550 rooms, derived from SUNCG | JSON polygon vertices, room categories and bounding boxes; raster previews | Room/outer geometry; lacks architectural doors/windows, dimensions metadata, plot and road semantics | Repository reports MIT; upstream SUNCG provenance warrants additional review | Adapter included for controlled research; do not assume commercial clearance from the repository badge alone |
| [ResPlan](https://github.com/m-agour/ResPlan) | 17,000 residential plans | Metric vector polygons plus typed room-connectivity graphs and 17 semantic categories | Walls, doors, windows, balconies and metre-scale coordinates; no parcel/road/setback ground truth | CC BY 4.0 data and MIT code in the release | Best current candidate for polygon/graph proposal experiments, with attribution and provenance review |
| [Modified Swiss Dwellings](https://archilyse.standfest.science/modified-swiss-dwellings) | 5,372 floors / 18,902 dwelling units, oriented to multi-unit buildings | WKT vector geometry, semantic areas, separators and openings; graph-ready | Walls, doors, windows and metric geometry; limited parcel/road context | Derived Swiss Dwellings material is reported under CC BY 4.0; verify the exact downloaded release | Strong secondary benchmark for geometry and building-complex generalization |

No dataset above provides dependable local setbacks, road access, construction codes, budgets, and full accessibility requirements together. Those remain specification/rule inputs rather than learned ground truth.

## Generation research

- [HouseDiffusion (CVPR 2023)](https://openaccess.thecvf.com/content/CVPR2023/papers/Shabani_HouseDiffusion_Vector_Floorplan_Generation_via_a_Diffusion_Model_With_Discrete_CVPR_2023_paper.pdf) generates vector room/door polygon loops conditioned on a bubble graph. Its mixed discrete/continuous denoising directly targets corner incidence, orthogonality, and shared structure. It is more relevant than raster-only image synthesis, but still needs a deterministic validity gate and dataset/license work.
- [Constrained Layout Generation with Factor Graphs (CVPR 2024)](https://openaccess.thecvf.com/content/CVPR2024/papers/Dupty_Constrained_Layout_Generation_with_Factor_Graphs_CVPR_2024_paper.pdf) models room boundaries with multiple latent variables and explicit spatial factors. This supports the decision to separate a proposal model from hard architectural constraints.
- [GSDiff (2024)](https://arxiv.org/abs/2408.16258) proposes wall junctions and segments as a structural graph before room polygons. It is promising for wall consistency but adds training and reconstruction complexity.
- [Unified Vector Floorplan Generation via Markup Representation (CVPR 2026)](https://openaccess.thecvf.com/content/CVPR2026/html/Shiohara_Unified_Vector_Floorplan_Generation_via_Markup_Representation_CVPR_2026_paper.html) represents heterogeneous conditioning and vector floor plans as a structured grammar for next-token prediction. It reinforces using a serialized structured plan rather than pixels, but a production adoption needs released code/weights, licensing, and local evaluation.

## Geometry and optimization libraries

[Shapely](https://github.com/shapely/shapely) is BSD-3-Clause and wraps GEOS for robust polygon predicates, clipping, offsets, unions, validity repair, and spatial indexing. It is already compatible with the Python service and is now the topology kernel. [Google OR-Tools](https://github.com/google/or-tools) is Apache-2.0 and is a good later option for integer room-dimension/no-overlap models; it is not added yet because bounded backtracking is sufficient for the current room counts and avoids another large runtime dependency.

## Decision

The production path is hybrid: a deterministic polygonal baseline now; normalized ResPlan/MSD experiments next; then a small conditional vector proposer only if it beats the baseline on held-out geometry, architecture, requirement, plot, and diversity metrics. Raster imagery may support parsing or qualitative diagnostics, but never becomes the canonical plan.
