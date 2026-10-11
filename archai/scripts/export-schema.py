"""Generate cross-language schema files from the authoritative Pydantic models."""
import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'apps/api'))
from app.schemas import HouseSpecification,HouseLayout,Operation
destination=root/'packages/architectural-schema'
destination.mkdir(parents=True,exist_ok=True)
for model in (HouseSpecification,HouseLayout,Operation):
    (destination/f'{model.__name__}.schema.json').write_text(json.dumps(model.model_json_schema(),indent=2),encoding='utf-8')
print('Exported 3 authoritative JSON schemas.')
