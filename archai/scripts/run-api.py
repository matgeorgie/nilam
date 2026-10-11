import json,os,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[1]
(root/'logs').mkdir(exist_ok=True)
(root/'logs/api-runtime.json').write_text(json.dumps({'pid':os.getpid(),'path':getattr(sys,'_base_executable',sys.executable),'started':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
sys.path.insert(0,str(root/'apps/api'))
import uvicorn
uvicorn.run('app.main:app',host='127.0.0.1',port=8000)
