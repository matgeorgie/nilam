"""Generate 100 varied valid plans and report footprint diversity."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps'/'api'))
from app.layout import DeterministicLayoutEngine,InfeasibleLayout
from app.schemas import HouseShape,HouseSpecification,RoomRequirement
from app.research.evaluation import diversity_report,evaluate_layout

def build_spec(index:int)->HouseSpecification:
    shapes=[HouseShape.RECTANGLE,HouseShape.L_SHAPE,HouseShape.T_SHAPE,HouseShape.U_SHAPE,HouseShape.C_SHAPE,HouseShape.STEPPED,HouseShape.COURTYARD]
    beds=1+index%4;floors=1+(index//4)%2
    return HouseSpecification(plot_width=30+(index%5)*4,plot_length=44+(index%7)*4,shape=shapes[index%len(shapes)],floors=floors,road_location=['south','east','north','west'][index%4],rooms=[RoomRequirement(type='bedroom',name='Bedroom',count=beds),RoomRequirement(type='bathroom',name='Bathroom',count=max(1,beds//2)),RoomRequirement(type='living',name='Living'),RoomRequirement(type='kitchen',name='Kitchen'),RoomRequirement(type='dining',name='Dining')],parking_spaces=index%2)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=100);parser.add_argument('--output',type=Path)
    args=parser.parse_args();engine=DeterministicLayoutEngine();layouts=[];failed=[];metrics=[]
    for index in range(args.count):
        last_error=None
        for retry in range(4):
            spec=build_spec(index);spec.plot_width+=retry*8;spec.plot_length+=retry*8
            try:
                layout=engine.generate(spec);layouts.append(layout);metrics.append(evaluate_layout(layout,spec));last_error=None;break
            except InfeasibleLayout as error:last_error=error
        if last_error:failed.append({'index':index,'shape':spec.shape.value,'reason':str(last_error)})
    result={'diversity':diversity_report(layouts),'valid_count':len(layouts),'failed_count':len(failed),'failures':failed,'plans':metrics}
    text=json.dumps(result,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(text)
    raise SystemExit(0 if result['diversity']['passes'] and not failed else 1)
if __name__=='__main__':main()
