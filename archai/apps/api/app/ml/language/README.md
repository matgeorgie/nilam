# Local language model

ArchAI now uses Qwen 3.5 9B through a local LM Studio server at `http://127.0.0.1:1234/v1`. The loaded model ID is `qwen/qwen3.5-9b`. Override the URL or model ID with `ARCHAI_LM_STUDIO_URL` and `ARCHAI_LM_STUDIO_MODEL` if needed.

The previous Qwen2.5 GGUF checkpoint may still be present on this device, but ArchAI no longer loads it. The guided form works without LM Studio; free-text requirements and chat edits require the server. Model responses are validated as structured requirements or edits, and layout constraints are checked separately before a design is saved.
