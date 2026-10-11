"""Generate checked SVG examples from the same geometry used by the application."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps'/'api'))
from app.exports import drawing_export
from app.layout import DeterministicLayoutEngine
from app.research.evaluation import evaluate_layout
from app.schemas import HouseShape
from app.services import demo_spec

def main():
    output=ROOT/'docs'/'examples';output.mkdir(parents=True,exist_ok=True)
    engine=DeterministicLayoutEngine();manifest=[]
    for shape in (HouseShape.RECTANGLE,HouseShape.L_SHAPE,HouseShape.T_SHAPE,HouseShape.U_SHAPE,HouseShape.C_SHAPE,HouseShape.STEPPED,HouseShape.COURTYARD):
        spec=demo_spec().model_copy(deep=True);spec.shape=shape
        layout=engine.generate(spec);data,_=drawing_export(layout,'svg')
        filename=f'{shape.value}-plan.svg';(output/filename).write_bytes(data)
        manifest.append({'file':filename,**evaluate_layout(layout,spec)})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Generated {len(manifest)} validated SVG plans in {output}')
if __name__=='__main__':main()
