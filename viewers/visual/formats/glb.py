from ...core import ViewerError
from pathlib import Path

def load_glb(path,context=None,include_scene=False):
    """Bounded, embedded-only static triangle geometry; never resolves URIs."""
    import json, struct, math
    from array import array
    from PySide6.QtGui import QMatrix4x4, QVector3D, QQuaternion
    try:
        if context: context.check()
        with Path(path).open('rb') as f: raw = f.read(64*1024*1024+1)
        if len(raw)>64*1024*1024: raise OverflowError('Лимит GLB — 64 MiB')
        if len(raw)<20 or struct.unpack_from('<4sII',raw) != (b'glTF',2,len(raw)): raise ValueError('Неверный заголовок GLB 2.0')
        chunks=[]; offset=12
        while offset<len(raw):
            size,kind=struct.unpack_from('<II',raw,offset); offset+=8
            if size%4 or offset+size>len(raw): raise ValueError('Повреждённый блок GLB')
            chunks.append((kind,raw[offset:offset+size])); offset+=size
        if len(chunks)!=2 or chunks[0][0]!=0x4e4f534a or chunks[1][0]!=0x004e4942: raise ValueError('Ожидаются JSON и BIN')
        if len(chunks[0][1])>4*1024*1024: raise OverflowError('Лимит JSON сцены — 4 MiB')
        doc=json.loads(chunks[0][1]); binary=chunks[1][1]
        if doc['asset']['version']!='2.0' or doc.get('extensionsRequired'): raise ValueError('Не поддерживаются обязательные расширения glTF')
        buffers=doc['buffers']
        if len(buffers)!=1 or 'uri' in buffers[0] or not 0<=buffers[0]['byteLength']<=len(binary): raise ValueError('Требуется встроенный BIN без внешних буферов')
        binary=binary[:buffers[0]['byteLength']]
        def index(items,key):
            if type(key)!=int or not 0<=key<len(items): raise ValueError('Индекс вне диапазона')
            return items[key]
        def accessor(key,position=False):
            a=index(doc['accessors'],key)
            if 'sparse' in a or a.get('normalized'): raise ValueError('Sparse / normalized accessor не поддерживается')
            component=a['componentType']; count=a['count']
            if type(count)!=int or not 0<count<=600000: raise OverflowError('Лимит accessor — 600000 элементов')
            if position:
                if component!=5126 or a['type']!='VEC3': raise ValueError('POSITION должен быть FLOAT VEC3')
                fmt='<fff'
            else:
                if a['type']!='SCALAR' or component not in (5121,5123,5125): raise ValueError('Неподдерживаемые индексы')
                fmt={5121:'<B',5123:'<H',5125:'<I'}[component]
            v=index(doc['bufferViews'],a['bufferView']); start=v.get('byteOffset',0); length=v['byteLength']
            width=struct.calcsize(fmt); stride=v.get('byteStride',width); local=a.get('byteOffset',0)
            if v['buffer']!=0 or min(start,length,local)<0 or stride<width or stride>252 or start+length>len(binary) or local+(count-1)*stride+width>length: raise ValueError('Accessor выходит за границы BIN')
            result=[struct.unpack_from(fmt,binary,start+local+i*stride) for i in range(count)]
            if position and any(not math.isfinite(x) or abs(x)>1e12 for p in result for x in p): raise ValueError('Некорректные координаты')
            return result if position else [p[0] for p in result]
        nodes=doc.get('nodes',[])
        if len(nodes)>10000: raise OverflowError('Лимит — 10000 узлов')
        roots=index(doc['scenes'],doc.get('scene',0)).get('nodes',[])
        vertices=array('f'); material_ids=[]; points=[]; objects=0; triangle_count=0; source_vertices=0; visited=set()
        material_definitions=doc.get('materials',[])
        if len(material_definitions)>32: raise ValueError('Лимит — 32 GLB материала')
        def visit(key,parent,ancestors):
            nonlocal objects,triangle_count,source_vertices
            if context: context.check()
            if key in ancestors or key in visited or len(ancestors)>100: raise ValueError('Цикл или повтор узла сцены')
            visited.add(key); n=index(nodes,key)
            if 'skin' in n: raise ValueError('Skinning не поддерживается; экспортируйте статическую модель')
            local=QMatrix4x4()
            if 'matrix' in n:
                m=n['matrix']
                if len(m)!=16: raise ValueError('Неверная матрица')
                local=QMatrix4x4(*[m[col*4+row] for row in range(4) for col in range(4)])
            else:
                local.translate(*n.get('translation',[0,0,0]))
                q=n.get('rotation',[0,0,0,1]); local.rotate(QQuaternion(q[3],q[0],q[1],q[2]))
                local.scale(*n.get('scale',[1,1,1]))
            transform=parent*local
            if 'mesh' in n:
                objects+=1
                for p in index(doc['meshes'],n['mesh'])['primitives']:
                    if p.get('mode',4)!=4 or p.get('targets') or p.get('extensions'): raise ValueError('Поддерживаются статические TRIANGLES без сжатия')
                    positions=accessor(p['attributes']['POSITION'],True)
                    normals=accessor(p['attributes']['NORMAL'],True) if 'NORMAL' in p['attributes'] else None
                    if normals is not None and len(normals)!=len(positions): raise ValueError('NORMAL и POSITION должны иметь одинаковую длину')
                    normal_transform=transform.inverted()[0].transposed()
                    material=p.get('material',-1)
                    if type(material)!=int or material<-1 or material>=len(material_definitions): raise ValueError('Неверный GLB material index')
                    source_vertices+=len(positions)
                    indices=accessor(p['indices']) if 'indices' in p else list(range(len(positions)))
                    if len(indices)%3: raise ValueError('Неполный треугольник')
                    triangle_count+=len(indices)//3
                    if triangle_count>200000: raise OverflowError('Лимит — 200000 треугольников')
                    transformed=[transform.map(QVector3D(*v)) for v in positions]
                    for i in range(0,len(indices),3):
                        if context and i%768==0: context.check()
                        abc=[index(transformed,k) for k in indices[i:i+3]]
                        if include_scene: material_ids.append(material)
                        normal=QVector3D.crossProduct(abc[1]-abc[0],abc[2]-abc[0]).normalized()
                        for corner,v in enumerate(abc):
                            vertex_normal=normal_transform.mapVector(QVector3D(*normals[indices[i+corner]])).normalized() if normals is not None else normal
                            point=(v.x(),v.y(),v.z())
                            if any(not math.isfinite(x) or abs(x)>1e15 for x in point): raise ValueError('Неверное преобразование узла')
                            points.append(point); vertices.extend((*point,vertex_normal.x(),vertex_normal.y(),vertex_normal.z()))
            for child in n.get('children',[]): visit(child,transform,ancestors|{key})
        for key in roots: visit(key,QMatrix4x4(),set())
        if not points: raise ValueError('В сцене нет геометрии')
        low=[min(p[i] for p in points) for i in range(3)]; high=[max(p[i] for p in points) for i in range(3)]
        center=[(a+b)/2 for a,b in zip(low,high)]; radius=math.sqrt(sum((b-a)**2 for a,b in zip(low,high)))/2
        if radius<1e-12: raise ValueError('Нулевой размер модели')
        for i in range(0,len(vertices),6):
            for axis in range(3): vertices[i+axis]=(vertices[i+axis]-center[axis])/radius
        info=dict(vertices=source_vertices,triangles=triangle_count,objects=objects,bytes=len(raw))
        if include_scene:
            from ..contracts import SceneData
            from .gltf_materials import read_materials
            materials=read_materials(material_definitions)
            return SceneData(vertices.tobytes(),dict(info,format='GLB',materials=len(materials)),materials,tuple(material_ids),bytes(triangle_count*36))
        return vertices,info
    except (MemoryError,OverflowError) as exc: raise ViewerError('CLAP-RENDER-004',exc,file=path) from exc
    except Exception as exc:
        from ..contracts import AssetFailure
        if isinstance(exc,AssetFailure): raise
        raise ViewerError('CLAP-RENDER-001',exc,file=path) from exc

class GlbLoader:
    def probe(self,header): return header.startswith(b'glTF')
    def load(self,path,context):
        from ..contracts import Asset
        data=load_glb(path,context,include_scene=True)
        caps={'view.move','view.zoom','view.rotate'}
        if data.materials: caps.add('view.materials')
        notices=tuple(dict.fromkeys(n for material in data.materials for n in material.notices))
        return Asset(data,frozenset(caps),data.info,notices)
