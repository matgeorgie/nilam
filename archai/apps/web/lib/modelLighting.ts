import type {Layout} from './types';

export function lightingFrame(layout:Pick<Layout,'width'|'length'|'floors'>,floorHeight:number){
 const extent=Math.max(layout.width,layout.length)/2+8;
 return {
  shadowExtent:extent,
  shadowFar:Math.max(100,layout.floors*floorHeight+80),
  contactScale:Math.max(layout.width,layout.length)*1.5,
  contactFar:layout.floors*floorHeight+10,
  sunPosition:[-layout.width*.6,Math.max(45,layout.floors*floorHeight+35),-layout.length*.45] as [number,number,number],
 };
}
