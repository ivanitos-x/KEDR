"""Translate a bounded, whitelisted Blender node subset to material domain data.

The resulting data is interpreted by our renderer, never by Blender or Python eval.
"""
import math
from ..contracts import MaterialData,MaterialOp

class UnsupportedMaterial(ValueError): pass

def read_material(file,address):
    material=file.records(address,'Material')[0]
    identifier=material.get('id'); name=identifier.get('name','Материал') if identifier.has('name') else 'Материал'
    if isinstance(name,int): name='Материал'
    name=str(name)[2:] if str(name).startswith('MA') else str(name)
    nodes=[]; cache={}; visiting=set()
    def add(op,args=(),values=()):
        if len(nodes)>=256: raise UnsupportedMaterial('Лимит — 256 операций материала')
        values=tuple(float(x) for x in values)
        if any(not math.isfinite(x) or abs(x)>1e6 for x in values): raise UnsupportedMaterial('Некорректные параметры материала')
        nodes.append(MaterialOp(op,tuple(args),values)); return len(nodes)-1
    def constant(value):
        if isinstance(value,(float,int)): value=(value,)*4
        if len(value)==3: value=(*value,1)
        return add('constant',values=value)
    def linked(first,kind):
        seen=set()
        while first:
            file.check()
            if first in seen or len(seen)>=256: raise UnsupportedMaterial('Цикл или чрезмерная цепочка узлов')
            seen.add(first); record=file.records(first,kind)[0]; yield first,record; first=record.get('next',0)
    tree_pointer=material.get('nodetree',0)
    if not tree_pointer or not material.get('use_nodes',0):
        color=constant(tuple(material.get(k,.8) for k in ('r','g','b'))+(1,))
        return MaterialData(name,tuple(nodes)+(MaterialOp('constant',values=(.5,)*4),MaterialOp('constant',values=(0,)*4)),color,len(nodes),len(nodes)+1)
    try:
        tree=file.records(tree_pointer,'bNodeTree')[0]
        tree_nodes=dict(linked(tree.get('nodes').get('first'),'bNode'))
        links={link.get('tosock'):(link.get('fromnode'),link.get('fromsock')) for _,link in linked(tree.get('links').get('first'),'bNodeLink')}
        sockets={}; inputs={}; outputs={}
        for pointer,node in tree_nodes.items():
            inputs[pointer]=dict(linked(node.get('inputs').get('first'),'bNodeSocket'))
            outputs[pointer]=dict(linked(node.get('outputs').get('first'),'bNodeSocket'))
            sockets.update(inputs[pointer]); sockets.update(outputs[pointer])
        def socket_value(pointer):
            socket=sockets[pointer]; kind=socket.get('type'); value=socket.get('default_value')
            if not value: return constant(0)
            record_type={0:'bNodeSocketValueFloat',1:'bNodeSocketValueVector',2:'bNodeSocketValueRGBA'}.get(kind)
            if record_type is None: raise UnsupportedMaterial('Неподдерживаемый socket')
            return constant(file.records(value,record_type)[0].get('value'))
        def input_node(pointer,identifier,default=None):
            found=next((a for a,s in inputs[pointer].items() if s.get('identifier')==identifier or s.get('name')==identifier),None)
            if found is None:
                if default is None: raise UnsupportedMaterial('Не найден вход '+identifier)
                return constant(default)
            if found not in links: return socket_value(found)
            source,source_socket=links[found]
            result=output_node(source,source_socket)
            if sockets[found].get('type')==0 and sockets[source_socket].get('type') in (1,2): result=add('luminance',(result,))
            return result
        def output_node(pointer,socket):
            key=(pointer,socket)
            if key in cache: return cache[key]
            if key in visiting or len(visiting)>32: raise UnsupportedMaterial('Цикл или чрезмерная глубина материала')
            if pointer not in tree_nodes or socket not in outputs[pointer]: raise UnsupportedMaterial('Ссылка вне дерева материала')
            visiting.add(key); node=tree_nodes[pointer]; kind=node.get('idname'); output=sockets[socket].get('identifier')
            if kind=='ShaderNodeTexCoord':
                if output not in ('Generated','Object'): raise UnsupportedMaterial('Координаты '+output+' пока не поддерживаются')
                result=add('generated' if output=='Generated' else 'object')
            elif kind=='ShaderNodeMapping':
                if node.get('custom1',0)!=0: raise UnsupportedMaterial('Поддерживается Mapping Point')
                result=add('mapping',tuple(input_node(pointer,s) for s in ('Vector','Location','Rotation','Scale')))
            elif kind=='ShaderNodeTexNoise':
                storage=file.records(node.get('storage'),'NodeTexNoise')[0]
                if storage.get('dimensions')!=3 or storage.get('type',1)!=1 or not storage.get('normalize',1): raise UnsupportedMaterial('Поддерживается только нормализованный Noise 3D fBM')
                vector_socket=next((a for a,s in inputs[pointer].items() if s.get('identifier')=='Vector'),None)
                vector=input_node(pointer,'Vector') if vector_socket in links else add('generated')
                noise_key=(pointer,'internal_noise')
                if noise_key not in cache:
                    cache[noise_key]=add('noise',(vector,)+tuple(input_node(pointer,s,d) for s,d in [('Scale',5),('Detail',2),('Roughness',.5),('Lacunarity',2),('Distortion',0)]))
                result=add('noise_fac' if output=='Fac' else 'noise_color',(cache[noise_key],))
            elif kind=='ShaderNodeValToRGB':
                ramp=file.records(node.get('storage'),'ColorBand')[0]; count=ramp.get('tot'); interpolation=ramp.get('ipotype')
                if not 1<=count<=32 or ramp.get('color_mode',0)!=0 or interpolation not in (0,1,4): raise UnsupportedMaterial('Поддерживаются RGB Color Ramp: Linear/Ease/Constant, до 32 точек')
                stops=sorted(ramp.get('data')[:count],key=lambda r:r.get('pos'))
                values=[interpolation]
                for stop in stops: values.extend(stop.get(k) for k in ('pos','r','g','b','a'))
                result=add('ramp',(input_node(pointer,'Fac'),),values)
                if output=='Alpha': result=add('noise_fac',(result,))
            elif kind=='ShaderNodeMix':
                mix=file.records(node.get('storage'),'NodeShaderMix')[0]; mode=mix.get('blend_type')
                if mix.get('data_type')!=2 or mode not in (0,1,2,3,4,6,7,8): raise UnsupportedMaterial('Неподдерживаемый режим Mix')
                result=add('mix',tuple(input_node(pointer,s) for s in ('Factor_Float','A_Color','B_Color')),(mode,mix.get('clamp_factor',0),mix.get('clamp_result',0)))
            elif kind in ('ShaderNodeRGB','ShaderNodeValue'): result=socket_value(socket)
            elif kind=='NodeReroute': result=input_node(pointer,'Input')
            else: raise UnsupportedMaterial('Узел '+str(kind)+' пока не поддерживается')
            visiting.remove(key); cache[key]=result; return result
        output_nodes=[(a,n) for a,n in tree_nodes.items() if n.get('idname')=='ShaderNodeOutputMaterial']
        if len(output_nodes)!=1: raise UnsupportedMaterial('Нужен один Material Output')
        out=output_nodes[0][0]; surface=next((a for a,s in inputs[out].items() if s.get('identifier')=='Surface'),None)
        if surface not in links: raise UnsupportedMaterial('Material Output не подключён')
        principled=links[surface][0]
        if tree_nodes[principled].get('idname')!='ShaderNodeBsdfPrincipled': raise UnsupportedMaterial('Поддерживается Principled BSDF')
        color=input_node(principled,'Base Color'); rough=input_node(principled,'Roughness',.5); metal=input_node(principled,'Metallic',0)
        return MaterialData(name,tuple(nodes),color,rough,metal,('Процедурный Noise и освещение воспроизводятся приближённо; это не Eevee/Cycles.',))
    except (UnsupportedMaterial,KeyError,ValueError,IndexError) as exc:
        # A material failure does not prevent viewing geometry in Solid.
        nodes=[]; color=constant(tuple(material.get(k,.8) for k in ('r','g','b'))+(1,)); rough=constant(material.get('roughness',.5)); metal=constant(material.get('metallic',0))
        return MaterialData(name,tuple(nodes),color,rough,metal,('Материал упрощён до базового цвета: '+str(exc),))
