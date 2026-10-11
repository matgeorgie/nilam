import {CanvasTexture,RepeatWrapping,SRGBColorSpace,TextureLoader,Texture} from 'three';

export type Pattern='wood'|'tile'|'concrete'|'deck'|'plaster';
export type SurfaceFinish={color:string;roughness:number;metalness:number;pattern:Pattern};

const wood:SurfaceFinish={color:'#c4aa88',roughness:.84,metalness:0,pattern:'wood'};
const tile:SurfaceFinish={color:'#ddd9cf',roughness:.67,metalness:0,pattern:'tile'};
const deck:SurfaceFinish={color:'#ad9474',roughness:.83,metalness:0,pattern:'deck'};
const concrete:SurfaceFinish={color:'#aeb3b4',roughness:.9,metalness:0,pattern:'concrete'};
const floors:Record<string,SurfaceFinish>={bedroom:wood,living:wood,dining:wood,office:wood,hall:wood,kitchen:tile,bathroom:{...tile,color:'#d6ddda',roughness:.58},utility:tile,parking:concrete,balcony:deck,veranda:deck,porch:deck};
export const interiorWall:SurfaceFinish={color:'#f3f0e9',roughness:.92,metalness:0,pattern:'plaster'};
export const exteriorWall:SurfaceFinish={color:'#e7e3db',roughness:.91,metalness:0,pattern:'plaster'};
export function floorFinish(type:string):SurfaceFinish{return floors[type]||concrete}

const textures=new Map<Pattern,CanvasTexture>();
export function surfaceTexture(pattern:Pattern):CanvasTexture|null{
 if(typeof document==='undefined')return null;
 const cached=textures.get(pattern);if(cached)return cached;
 const canvas=document.createElement('canvas');canvas.width=canvas.height=256;
 const ctx=canvas.getContext('2d');if(!ctx)return null;
 ctx.fillStyle='#f3f1ed';ctx.fillRect(0,0,256,256);
 if(pattern==='wood'||pattern==='deck'){
  const spacing=pattern==='wood'?42:30;ctx.strokeStyle='#c8c3ba';ctx.lineWidth=2;
  for(let y=0;y<=256;y+=spacing){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(256,y);ctx.stroke()}
  if(pattern==='wood')for(let row=0;row<7;row++)for(let x=(row%2)*98;x<256;x+=196){ctx.beginPath();ctx.moveTo(x,row*spacing);ctx.lineTo(x,(row+1)*spacing);ctx.stroke()}
 }else if(pattern==='tile'){
  ctx.strokeStyle='#c2c6c4';ctx.lineWidth=3;
  for(let p=0;p<=256;p+=64){ctx.beginPath();ctx.moveTo(p,0);ctx.lineTo(p,256);ctx.moveTo(0,p);ctx.lineTo(256,p);ctx.stroke()}
 }else{
  ctx.fillStyle=pattern==='plaster'?'#e6e4e0':'#d8d8d5';
  for(let i=0;i<260;i++){const x=(i*97+31)%256,y=(i*151+17)%256;ctx.fillRect(x,y,pattern==='plaster'?1:2,pattern==='plaster'?1:2)}
 }
 const texture=new CanvasTexture(canvas);texture.wrapS=texture.wrapT=RepeatWrapping;
 const feetPerRepeat=pattern==='tile'?2.5:pattern==='plaster'?3:4;
 texture.repeat.set(1/feetPerRepeat,1/feetPerRepeat);texture.colorSpace=SRGBColorSpace;texture.anisotropy=4;
 textures.set(pattern,texture);return texture;
}

const photoTextures=new Map<string,Texture>();
export function photoTexture(pattern:Pattern,channel:'diff'|'nor_gl'|'rough'='diff'):Texture|null{
 if(typeof document==='undefined')return null;
 const asset=pattern==='wood'?'wood_floor_deck':pattern==='deck'?'brown_planks_03':null;
 if(!asset)return null;
 const key=asset+channel;if(photoTextures.has(key))return photoTextures.get(key)!;
 const texture=new TextureLoader().load(`/materials/${asset}/${channel}.jpg`);
 texture.wrapS=texture.wrapT=RepeatWrapping;texture.repeat.set(1/6,1/6);texture.anisotropy=4;
 if(channel==='diff')texture.colorSpace=SRGBColorSpace;
 photoTextures.set(key,texture);return texture;
}
