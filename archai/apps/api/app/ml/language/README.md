# Local language model

ArchAI uses the official Qwen2.5-1.5B-Instruct Q4_K_M GGUF directly through llama-cpp-python 0.3.36. Inference runs in the Python process on CPU (four threads, 4096-token context); there is no hosted AI inference call, local HTTP model server, or production rule-parser fallback.

Official model: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
Pinned revision: 91cad51170dc346986eccefdc2dd33a9da36ead9
File: qwen2.5-1.5b-instruct-q4_k_m.gguf
Bytes: 1117320736
SHA256: 6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e
License: Apache-2.0 (upstream Qwen model terms).
Runtime: https://github.com/abetlen/llama-cpp-python

Run scripts/Install-LocalAI.ps1 to install/download on another computer. The source archive excludes this large GGUF file; it is already installed in this laptop's working project. The downloader verifies the pinned hash. After installation, inference does not need internet.

The small model is imperfect. Per-floor forms are the authoritative requirements; extracted text must be reviewed. Site settings are never overwritten by description inference. Malformed output requests guided input. Chat reference validation prevents choosing an arbitrary bedroom when several match. No model is allowed to declare geometry valid; geometry/access checks decide whether a revision is saved.
