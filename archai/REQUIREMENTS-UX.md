# A simpler requirements workflow for ArchAI

## Decision and evidence

Use a guided, structured brief as the primary input. Keep actual local AI for bounded design edits after a plan exists. Do not make model extraction a prerequisite for generation.

The old screen required users to write a long description, wait for CPU inference, understand partial extraction failures, then review nine numerical room fields on every floor. Earlier local tests found incorrect room extraction and a 90-second timeout even for a simple reading. These observations apply to this installed small model and configuration, not to all language models.

[GOV.UK question pages](https://design-system.service.gov.uk/patterns/question-pages/) recommend starting with one thing per page to focus the user's answer. ArchAI applies this as a small group of related site questions, followed by one floor at a time. [Check answers](https://design-system.service.gov.uk/patterns/check-answers/) supports a final editable review before submission. [NN/g recognition and recall](https://www.nngroup.com/articles/recognition-and-recall/) supports providing visible choices instead of making users remember syntax or write a complete brief. [Progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) supports moving uncommon options behind an expandable control. These are general usability principles; they do not establish that ArchAI has passed a human usability study.

## Alternatives evaluated

| Approach | Strength | Limitation for this project | Decision |
|---|---|---|---|
| One large text description | Flexible, familiar | The installed 1.5B model has misread counts/ownership and can time out; users must diagnose its output | Removed from the required creation flow |
| Entirely AI-driven interview | Can ask contextual follow-ups | Requires dependable dialogue state and repeated slow inference; can invent defaults or skip questions | Future optional assistant, not a dependency |
| Guided visual questions and editable review | Exact floor/count/bathroom ownership, immediate response, little typing | Does not capture every spatial relationship automatically | Implemented as the primary flow |
| Local voice input | Helps users who find typing difficult | Transcription cannot resolve unclear floor assignments or ensuite ownership; adds memory and latency | Optional future enhancement |

A larger model is not a substitute for a usable input flow. The official [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) documents the actual available quantized model. ArchAI retains its installed local Qwen runtime for chat rather than downloading another unbenchmarked model on an 8 GB RAM laptop.

For future voice support, use an actual local Whisper model, such as base, with a reviewed transcript. The [official Whisper repository](https://github.com/openai/whisper) documents local execution and the available model sizes. Voice has not been implemented in this update. Do not silently use browser speech recognition or a cloud transcription service when offline inference is required.

## Implemented user journey

1. Plot: name, dimensions, units, and a visual road-side selector. Setbacks, irregular polygons, and footprint selection sit under optional advanced settings.
2. Floors: select one to four floors using cards. Ground floor terminology is explicit.
3. Rooms: work through one floor at a time. Use plus/minus room counters. Assign private bathrooms to individual bedrooms; shared bathrooms are counted separately. Add utility, office, sit-out and balcony only when needed. Ground-floor parking is shown once.
4. Review: inspect plot and floor requirements, including named bedrooms and their attached bathrooms. Change links go directly to the relevant question.
5. Generate: confirmed structured requirements go directly to the existing local generation pipeline. The creation flow makes no language-extraction call.
6. Edit: the existing local Qwen chat and guided requirements editor remain available in the workspace.

A compact-home and family-duplex starting brief are optional. They are explicitly labelled examples, not AI-generated recommendations, and they disclose that they replace plot/room choices. Rectangle is the default because it is better supported by this planner. Other footprints remain available under advanced settings, with an experimental label.

The dialog keeps Back/Continue controls visible on small screens, traps keyboard focus, closes on Escape when not generating, and focuses each new question heading. Failed generation keeps answers and permits editing. Retrying reuses the newly created project rather than producing duplicate failed projects. Raw planner diagnostics remain available under Show planner details.

## Technology and model boundaries

React UI -> typed HouseSpecification -> existing local HouseGAN adapter and geometric planning/validation -> saved vector 2D layout -> existing 3D scene/walkthrough.

The form is ordinary structured input, not a rule-based natural-language parser and not a simulated AI conversation. No hosted model inference API is added. Local HTTP endpoints connect this browser to the Python app; model inference itself remains on the computer.

Local Qwen chat -> schema-constrained typed edit proposal -> exact room reference resolution -> validated geometry operation or regeneration -> saved revision.

[llama.cpp grammar documentation](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md) documents JSON-schema-based constrained generation. Our inference is that constraining JSON syntax cannot by itself prove that a room count or floor assignment matches a user's intention. Keep a confirmed brief as the source of truth and request clarification for ambiguous edits. Do not silently override user counts based on AI suggestions.

## Verification and remaining limits

Browser checks cover exact per-floor payloads, ensuite ownership, road side, closed kitchen preservation, editing from review, failed-generation recovery, retry without duplicates, mobile overflow, keyboard focus, and absence of extraction requests. Real compact-home and family-duplex generation and walkthrough are exercised against the running backend. TypeScript is checked separately.

The current planner still cannot satisfy every shape or combination. This change improves capture and recovery; it does not replace the geometric planner or make an architectural approval claim. No new language-model accuracy benchmark or speech feature is claimed. Human usability testing remains the next validation step: ask several first-time users to enter a supplied brief without coaching, and record completion, corrections, missing fields, and generation success.
