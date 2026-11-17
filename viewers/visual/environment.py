"""Explicit user-selected Radiance RGBE input, bounded and without external resources."""
from dataclasses import dataclass
import re
from .contracts import AssetFailure

@dataclass(frozen=True)
class EnvironmentData:
    width:int
    height:int
    rgbe:bytes

def load_hdr(path,context=None):
    try:
        if context: context.check()
        with path.open('rb') as f:
            raw=f.read(16*1024*1024+1)
        if len(raw)>16*1024*1024: raise ValueError('Лимит HDRI — 16 MiB')
        if not raw.startswith((b'#?RADIANCE\n',b'#?RGBE\n')): raise ValueError('Ожидается Radiance HDR RGBE')
        split=raw.find(b'\n\n')
        if split<0 or split>8192 or b'FORMAT=32-bit_rle_rgbe' not in raw[:split]: raise ValueError('Неподдерживаемый HDRI header')
        pos=split+2; end=raw.find(b'\n',pos)
        match=re.fullmatch(rb'-Y (\d+) \+X (\d+)',raw[pos:end])
        if not match: raise ValueError('Поддерживается ориентация HDRI -Y +X')
        height,width=map(int,match.groups()); pos=end+1
        if not 1<=width<=2048 or not 1<=height<=1024: raise ValueError('Лимит HDRI — 2048 × 1024')
        pixels=bytearray(width*height*4)
        for y in range(height):
            if context:
                context.check()
                if y%32==0: context.progress(f'HDRI: строка {y+1} из {height}…')
            if raw[pos:pos+2]==b'\x02\x02' and width>=8:
                if pos+4>len(raw) or int.from_bytes(raw[pos+2:pos+4],'big')!=width: raise ValueError('Повреждённая HDR scanline')
                pos+=4
                for channel in range(4):
                    x=0
                    while x<width:
                        if pos>=len(raw): raise ValueError('Оборванная HDR scanline')
                        count=raw[pos]; pos+=1
                        if count>128:
                            count-=128
                            if not count or x+count>width or pos>=len(raw): raise ValueError('Неверная HDR RLE серия')
                            values=bytes([raw[pos]])*count; pos+=1
                        else:
                            if count==0 or x+count>width or pos+count>len(raw): raise ValueError('Неверная HDR RLE серия')
                            values=raw[pos:pos+count]; pos+=count
                        for value in values: pixels[(y*width+x)*4+channel]=value; x+=1
            else:
                size=width*4
                if pos+size>len(raw): raise ValueError('Оборванный HDR RGBE массив')
                line=raw[pos:pos+size]
                if any(line[x:x+3]==b'\x01\x01\x01' for x in range(0,size,4)): raise ValueError('Legacy HDR repeat encoding не поддерживается')
                pixels[y*size:(y+1)*size]=line; pos+=size
        return EnvironmentData(width,height,bytes(pixels))
    except AssetFailure: raise
    except (OSError,ValueError) as exc:
        error=AssetFailure('invalid_input','CLAP-RENDER-009',str(exc)); error.file=str(path)
        raise error from exc

class RadianceLoader:
    def load(self,path,context=None): return load_hdr(path,context)
