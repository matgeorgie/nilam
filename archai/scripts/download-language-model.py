"""Download pinned official Qwen weights; never calls an inference API."""
from pathlib import Path
import hashlib,httpx
root=Path(__file__).resolve().parents[1]
path=root/'apps/api/app/ml/language/qwen2.5-1.5b-instruct-q4_k_m.gguf'
url='https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf'
if path.exists() and path.stat().st_size==1117320736:
    print('Qwen checkpoint is already installed.')
else:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.download')
    with httpx.stream('GET',url,follow_redirects=True,timeout=180) as response:
        response.raise_for_status()
        with temp.open('wb') as target:
            for chunk in response.iter_bytes(1024*1024):target.write(chunk)
    if temp.stat().st_size!=1117320736:raise RuntimeError('Incomplete model download.')
    temp.replace(path)
digest=hashlib.sha256()
with path.open('rb') as file:
    for chunk in iter(lambda:file.read(4*1024*1024),b''):digest.update(chunk)
if digest.hexdigest()!='6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e':raise RuntimeError('Model checksum does not match the pinned official checkpoint.')
print('Verified model SHA256:',digest.hexdigest())
