"""glTF metallic-roughness factors; texture resources are not opened."""
import math
from ..contracts import MaterialData,MaterialOp

def read_materials(definitions):
    if not isinstance(definitions,list) or len(definitions)>32: raise ValueError('Лимит — 32 GLB материала')
    materials=[]
    def factor(value):
        value=float(value)
        if not math.isfinite(value) or not 0<=value<=1: raise ValueError('Неверный glTF material factor')
        return value
    for definition in definitions:
        pbr=definition.get('pbrMetallicRoughness',{}); color=pbr.get('baseColorFactor',[1,1,1,1])
        if not isinstance(color,list) or len(color)!=4: raise ValueError('Неверный baseColorFactor')
        color=tuple(factor(c) for c in color); rough=factor(pbr.get('roughnessFactor',1)); metal=factor(pbr.get('metallicFactor',1))
        notices=[]
        if any(k in pbr for k in ('baseColorTexture','metallicRoughnessTexture')) or any(k in definition for k in ('normalTexture','occlusionTexture','emissiveTexture')):
            notices.append('GLB: используются material factors; texture/normal/AO карты пока не загружаются.')
        if definition.get('alphaMode','OPAQUE')!='OPAQUE' or color[3]!=1: notices.append('GLB: материал показан непрозрачным; alpha modes пока не поддержаны.')
        materials.append(MaterialData(str(definition.get('name','GLB material')),(MaterialOp('constant',values=color),MaterialOp('constant',values=(rough,)*4),MaterialOp('constant',values=(metal,)*4)),0,1,2,tuple(notices)))
    return tuple(materials)
