"""Native static .blend mesh loader. Blender/bpy never imported or launched."""
import math
import struct
from dataclasses import replace
from .blend_dna import BlendFile,read_bytes,invalid
from ..contracts import Asset,AssetFailure,Triangle,PolygonMesh,SubdivisionSettings
from ..geometry import triangles_to_scene,triangulate

IDENTITY=(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)
def multiply(a,b): return tuple(sum(a[r*4+k]*b[k*4+c] for k in range(4)) for r in range(4) for c in range(4))
def quaternion(q):
    w,x,y,z=q; length=math.sqrt(sum(v*v for v in q))
    if length<1e-15: raise invalid('Нулевая ориентация объекта')
    w,x,y,z=[v/length for v in q]
    return (1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w,0,2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w,0,2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y,0,0,0,0,1)
def transpose(m): return tuple(m[c*4+r] for r in range(4) for c in range(4))
def point(m,p): return tuple(sum(m[r*4+k]*p[k] for k in range(3))+m[r*4+3] for r in range(3))
def transformed_normal(m,n):
    a,b,c=m[:3]; d,e,f=m[4:7]; g,h,i=m[8:11]
    cofactor=(e*i-f*h,f*g-d*i,d*h-e*g,c*h-b*i,a*i-c*g,b*g-a*h,b*f-c*e,c*d-a*f,a*e-b*d)
    determinant=a*cofactor[0]+b*cofactor[1]+c*cofactor[2]
    if abs(determinant)<1e-20: return (0,0,1)
    result=[sum(cofactor[r*3+k]*n[k] for k in range(3))/determinant for r in range(3)]
    length=math.sqrt(sum(x*x for x in result))
    return tuple(x/length for x in result) if length>1e-20 else (0,0,1)

class BlendLoader:
    def __init__(self,subdivision=None): self.subdivision=subdivision
    def probe(self,header): return header.startswith((b'BLENDER',b'\x1f\x8b',b'\x28\xb5\x2f\xfd'))
    def load(self,path,context):
        try:
            f=BlendFile(read_bytes(path,context),context)
            return self.decode(f,context)
        except AssetFailure: raise
        except MemoryError as exc: raise AssetFailure('failed','CLAP-RENDER-004','Недостаточно памяти') from exc
        except Exception as exc: raise invalid('Неподдерживаемая или повреждённая структура .blend: '+str(exc)) from exc

    def decode(self,f,context):
        def records(ptr,name,count=1): return f.records(ptr,name,count)
        def ptr_array(ptr,count,fmt):
            if not 0<=count<=600000: raise invalid('Чрезмерное число элементов меша')
            size=struct.calcsize(f.endian+fmt)
            return list(struct.iter_unpack(f.endian+fmt,f.bytes_at(ptr,count*size)))
        def member(record,*names,default=None):
            for name in names:
                if record.has(name): return record.get(name)
            return default
        def layers(mesh,domain):
            data=member(mesh,*domain)
            if data is None: return {}
            count=data.get('totlayer',0)
            if not 0<=count<=1000: raise invalid('Слишком много CustomData layers')
            return {layer.get('name'):layer.get('data') for layer in records(data.get('layers'),'CustomDataLayer',count)} if count else {}
        def attributes(mesh):
            storage=mesh.get('attribute_storage')
            if storage is None: return {}
            count=storage.get('dna_attributes_num',0)
            if not 0<=count<=1000: raise invalid('Слишком много Attribute entries')
            result={}
            for attr in records(storage.get('dna_attributes'),'Attribute',count) if count else []:
                # NUL-terminated attribute names are read only from their containing block.
                address=attr.get('name'); block=f.by_address.get(address)
                if block is None or len(block[4])>1024: raise invalid('Некорректное имя атрибута')
                name=bytes(block[4]).split(b'\x00',1)[0].decode('utf-8')
                if name not in ('position','.corner_vert','material_index','crease_edge','crease_vert'): continue
                if attr.get('storage_type')!=0: raise AssetFailure('unsupported','CLAP-RENDER-005','Single-value attribute storage пока не поддерживается')
                array=records(attr.get('data'),'AttributeArray')[0]
                if array.get('is_single',0): raise AssetFailure('unsupported','CLAP-RENDER-005','Single-value attribute storage пока не поддерживается')
                result[name]=array.get('data')
            return result
        def mesh_geometry(obj,mesh):
            vertex_count=member(mesh,'verts_num','totvert',default=0); face_count=member(mesh,'faces_num','totpoly',default=0); corner_count=member(mesh,'corners_num','totloop',default=0)
            if not 0<vertex_count<=600000 or not 0<face_count<=200000 or not 0<corner_count<=600000: raise invalid('Пустой или чрезмерно большой меш')
            attrs=attributes(mesh); vlayers=layers(mesh,('vert_data','vdata')); clayers=layers(mesh,('corner_data','ldata'))
            position=attrs.get('position') or vlayers.get('position')
            if position: positions=ptr_array(position,vertex_count,'fff')
            else:
                mvert=mesh.get('mvert')
                if not mvert: raise AssetFailure('unsupported','CLAP-RENDER-005','Не найдены сохранённые позиции вершин')
                positions=[v.get('co') for v in records(mvert,'MVert',vertex_count)]
            if any(not math.isfinite(x) for p in positions for x in p): raise invalid('Некорректные координаты меша')
            low=[min(p[k] for p in positions) for k in range(3)]; high=[max(p[k] for p in positions) for k in range(3)]
            material_ptr=attrs.get('material_index') or layers(mesh,('face_data','pdata')).get('material_index')
            material_indices=[p[0] for p in ptr_array(material_ptr,face_count,'i')] if material_ptr else None
            corner=attrs.get('.corner_vert') or clayers.get('.corner_vert')
            if corner: corners=[x[0] for x in ptr_array(corner,corner_count,'i')]
            elif mesh.get('mloop'): corners=[v.get('v') for v in records(mesh.get('mloop'),'MLoop',corner_count)]
            else: raise AssetFailure('unsupported','CLAP-RENDER-005','Не найдены индексы углов граней')
            offset=member(mesh,'face_offset_indices','poly_offset_indices',default=0)
            if offset:
                values=[x[0] for x in ptr_array(offset,face_count+1,'i')]
                if values[0]!=0 or values[-1]!=corner_count: raise invalid('Неверные границы граней')
                faces=[(a,b-a) for a,b in zip(values,values[1:])]
            elif mesh.get('mpoly'):
                polys=records(mesh.get('mpoly'),'MPoly',face_count)
                faces=[(p.get('loopstart'),p.get('totloop')) for p in polys]
                if material_indices is None: material_indices=[p.get('mat_nr',0) for p in polys]
            else: raise AssetFailure('unsupported','CLAP-RENDER-005','Не найдены сохранённые грани')
            polygons=[]
            for face_number,(start,count) in enumerate(faces):
                f.check()
                if start<0 or count<3 or start+count>corner_count: raise invalid('Грань выходит за массив углов')
                ids=corners[start:start+count]
                if any(not 0<=i<vertex_count for i in ids): raise invalid('Неверный индекс вершины')
                polygons.append(tuple(ids))
            polygon_mesh=PolygonMesh(tuple(positions),tuple(polygons),tuple(material_indices or [0]*len(polygons)))
            smooth=False
            modifiers=obj.get('modifiers')
            for pointer,modifier in modifier_records(modifiers.get('first',0) if modifiers else 0):
                if not modifier.get('mode',0)&1 or modifier.get('mode',0)&(1<<31): continue
                if modifier.get('type')!=1:
                    notices.append('Модификатор '+str(modifier.get('name',''))+' не вычисляется; показан доступный результат остальных операций.')
                    continue
                sub=records(pointer,'SubsurfModifierData')[0]
                levels=sub.get('levels',0)
                if levels==0: continue
                if self.subdivision is None: raise AssetFailure('unavailable','CLAP-RENDER-006','Обработчик Subdivision Surface недоступен')
                if sub.get('flags',0)&16:
                    for name,count,domain in [('crease_vert',vertex_count,vlayers),('crease_edge',member(mesh,'edges_num','totedge',default=0),layers(mesh,('edge_data','edata')))]:
                        address=attrs.get(name) or domain.get(name)
                        if address and any(abs(v[0])>1e-8 for v in ptr_array(address,count,'f')):
                            raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: ненулевые crease weights пока не поддерживаются')
                    if mesh.get('medge') and 'crease' in f.fields.get('MEdge',{}):
                        edges=records(mesh.get('medge'),'MEdge',member(mesh,'edges_num','totedge',default=0))
                        if any(e.get('crease',0) for e in edges): raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: legacy crease weights пока не поддерживаются')
                kind={0:'catmull-clark',1:'simple'}.get(sub.get('subdivType'))
                result=self.subdivision.apply(polygon_mesh,SubdivisionSettings(levels,kind,sub.get('boundary_smooth',0)==1),context)
                polygon_mesh=result.mesh; notices.extend(result.notices)
                info.setdefault('subdivision',[]).append({'requested':levels,'applied':result.levels,'algorithm':kind})
                smooth=smooth or (kind=='catmull-clark' and result.levels>0)
            if smooth:
                normals=polygon_mesh.normals
            else: normals=None
            info['evaluated_vertices']=info.get('evaluated_vertices',0)+len(polygon_mesh.positions)
            for face_number,ids in enumerate(polygon_mesh.faces):
                if face_number%256==0: f.check()
                poly=[polygon_mesh.positions[i] for i in ids]
                for abc in triangulate(poly,context):
                    positions3=tuple(poly[i] for i in abc)
                    generated=tuple(tuple((p[k]-low[k])/max(high[k]-low[k],1e-12) for k in range(3)) for p in positions3)
                    yield positions3,generated,polygon_mesh.materials[face_number],tuple(normals[ids[i]] for i in abc) if normals else ()

        transforms={}
        def world(obj,address,chain=()):
            if address in transforms: return transforms[address]
            if address in chain or len(chain)>100: raise invalid('Цикл родительских объектов')
            if obj.has('obmat'): result=transpose(obj.get('obmat'))
            else:
                loc=obj.get('loc',(0,0,0)); delta=obj.get('dloc',(0,0,0)); scale=member(obj,'scale','size',default=(1,1,1)); ds=obj.get('dscale',(1,1,1))
                mode=obj.get('rotmode',1)
                def rotation(delta=False):
                    prefix='d' if delta else ''
                    if mode==0: return quaternion(obj.get(prefix+'quat',(1,0,0,0)))
                    if mode==-1:
                        axis=obj.get(prefix+'rotAxis',(0,0,1)); angle=obj.get(prefix+'rotAngle',0)/2; length=math.sqrt(sum(x*x for x in axis))
                        return quaternion((math.cos(angle),*[x*math.sin(angle)/length for x in axis])) if length>1e-15 else IDENTITY
                    angles=obj.get(prefix+'rot',(0,0,0)); order={1:'XYZ',2:'XZY',3:'YXZ',4:'YZX',5:'ZXY',6:'ZYX'}.get(mode)
                    if order is None: raise invalid('Неподдерживаемый Euler order')
                    result=IDENTITY
                    for axis in order:
                        i='XYZ'.index(axis); xyz=[0,0,0]; xyz[i]=math.sin(angles[i]/2)
                        result=multiply(quaternion((math.cos(angles[i]/2),*xyz)),result)
                    return result
                trs=list(IDENTITY)
                for i in range(3): trs[i*4+3]=loc[i]+delta[i]
                scaling=list(IDENTITY)
                for i in range(3): scaling[i*4+i]=scale[i]*ds[i]
                result=multiply(multiply(trs,multiply(rotation(True),rotation())),scaling)
                parent=obj.get('parent',0)
                if parent:
                    if obj.get('partype',0)!=0: raise AssetFailure('unsupported','CLAP-RENDER-005','Bone/vertex parenting не поддерживается')
                    result=multiply(multiply(world(records(parent,'Object')[0],parent,chain+(address,)),transpose(obj.get('parentinv',IDENTITY))),result)
            if any(not math.isfinite(x) for x in result): raise invalid('Неверная матрица объекта')
            transforms[address]=result; return result

        # Resolve the saved active scene and collection links without touching external paths.
        glob=next(f.typed_blocks('FileGlobal'),None); scene_address=glob.get('curscene',0) if glob else 0
        scene=records(scene_address,'Scene')[0] if scene_address else next(f.typed_blocks('Scene'),None)
        object_addresses=[]; collections=set()
        def linked(first,type_name):
            seen=set(); pointer=first
            while pointer:
                f.check()
                if pointer in seen or len(seen)>10000: raise invalid('Цикл списка сцены')
                seen.add(pointer); record=records(pointer,type_name)[0]; yield record; pointer=record.get('next',0)
        def modifier_records(first):
            seen=set()
            while first:
                f.check()
                if first in seen or len(seen)>64: raise invalid('Цикл или чрезмерный стек модификаторов')
                seen.add(first); modifier=records(first,'ModifierData')[0]; yield first,modifier; first=modifier.get('next',0)
        def collection(address,depth=0):
            if address in collections: return
            if depth>100 or len(collections)>10000: raise invalid('Слишком сложная коллекция')
            collections.add(address); record=records(address,'Collection')[0]
            objects=record.get('gobject')
            for link in linked(objects.get('first',0),'CollectionObject') if objects else []: object_addresses.append(link.get('ob'))
            children=record.get('children')
            for link in linked(children.get('first',0),'CollectionChild') if children else []: collection(link.get('collection'),depth+1)
        if scene is None or not scene.get('master_collection'): raise AssetFailure('unsupported','CLAP-RENDER-005','Поддерживаются сцены с Collections (Blender 2.80+)')
        collection(scene.get('master_collection'))
        object_addresses=list(dict.fromkeys(object_addresses)); info={'objects':0,'vertices':0,'format':'BLEND','version':f.version,'bytes':len(f.raw)}
        notices=['Subdivision Surface вычисляется локально в пределах бюджета; остальные модификаторы, Geometry Nodes, constraints и симуляции не вычисляются.']
        materials=[]; material_lookup={}
        def material_slots(obj,mesh):
            from .blend_materials import read_material
            count=mesh.get('totcol',0)
            if not 0<=count<=32: raise invalid('Лимит — 32 material slots')
            slots=[]
            pointers=ptr_array(mesh.get('mat'),count,'Q' if f.pointer==8 else 'I') if count else []
            overrides=obj.get('mat'); bits=obj.get('matbits'); object_count=obj.get('totcol',0)
            for i,pointer in enumerate(pointers):
                address=pointer[0]
                if overrides and bits and i<object_count and f.bytes_at(bits,object_count)[i]:
                    address=ptr_array(overrides,object_count,'Q' if f.pointer==8 else 'I')[i][0]
                if not address: slots.append(-1); continue
                if address not in material_lookup:
                    if len(materials)>=32: raise invalid('Лимит — 32 материала')
                    material_lookup[address]=len(materials)
                    material=read_material(f,address); materials.append(material); notices.extend(material.notices)
                slots.append(material_lookup[address])
            return slots
        def triangles():
            for address in object_addresses:
                f.check(); obj=records(address,'Object')[0]
                if obj.get('type')!=1: continue
                if obj.get('id').get('lib',0): raise AssetFailure('unsupported','CLAP-RENDER-005','Внешние linked-объекты не загружаются')
                mesh=records(obj.get('data'),'Mesh')[0]
                if mesh.get('id').get('lib',0): raise AssetFailure('unsupported','CLAP-RENDER-005','Внешний linked-меш не загружается')
                if member(mesh,'faces_num','totpoly',default=0)==0:
                    notices.append('Пустой или каркасный меш без граней пропущен.')
                    continue
                info['objects']+=1; info['vertices']+=member(mesh,'verts_num','totvert',default=0)
                transform=world(obj,address)
                slots=material_slots(obj,mesh)
                for abc,coordinates,material_index,normals in mesh_geometry(obj,mesh):
                    # Blender Z-up to common viewer Y-up; world position is preserved.
                    values=[point(transform,p) for p in abc]
                    transformed=[transformed_normal(transform,n) for n in normals]
                    yield Triangle(tuple((v[0],v[2],-v[1]) for v in values),coordinates,slots[material_index] if 0<=material_index<len(slots) else -1,tuple((n[0],n[2],-n[1]) for n in transformed))
        data=triangles_to_scene(triangles(),info,context)
        data=replace(data,materials=tuple(materials),info=dict(data.info,materials=len(materials)))
        capabilities={'view.move','view.zoom','view.rotate'}
        if materials: capabilities.add('view.materials')
        return Asset(data,frozenset(capabilities),data.info,tuple(dict.fromkeys(notices)))
