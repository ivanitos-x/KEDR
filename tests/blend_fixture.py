"""Small self-describing SDNA fixtures authored for these tests; no Blender needed."""
import struct
import re

def blend_fixture(path,modern=False,attributes=False,library=False,parented=False,material_slots=False,subdivision=0,viewport=True):
    schema={
      'ID':[('void','*lib')],
      'ListBase':[('void','*first'),('void','*last')],
      'ModifierData':[('ModifierData','*next'),('ModifierData','*prev'),('int','type'),('int','mode'),('char','name[64]')],
      'SubsurfModifierData':[('ModifierData','modifier'),('short','subdivType'),('short','levels'),('short','renderLevels'),('short','flags'),('short','boundary_smooth'),('short','_pad')],
      'MVert':[('float','co[3]')],
      'MPoly':[('int','loopstart'),('int','totloop'),('int','mat_nr')],
      'MLoop':[('int','v'),('int','e')],
      'AttributeStorage':[('Attribute','*dna_attributes'),('int','dna_attributes_num'),('int','_pad')],
      'Attribute':[('char','*name'),('short','data_type'),('char','domain'),('char','storage_type'),('char','_pad[4]'),('AttributeArray','*data')],
      'AttributeArray':[('void','*data'),('void','*sharing_info'),('int64_t','size')],
      'Material':[('ID','id'),('float','r'),('float','g'),('float','b'),('float','roughness'),('float','metallic'),('int','use_nodes'),('void','*nodetree')],
      'Mesh':[('ID','id'),('int','totvert'),('int','totpoly'),('int','totloop'),('int','_pad'),('MVert','*mvert'),('MPoly','*mpoly'),('MLoop','*mloop'),('int','*poly_offset_indices'),('AttributeStorage','attribute_storage'),('int','totcol'),('Material','**mat')],
      'Object':[('ID','id'),('short','type'),('short','rotmode'),('int','_pad'),('Mesh','*data'),('Object','*parent'),('float','parentinv[4][4]'),('float','loc[3]'),('float','size[3]'),('float','dscale[3]'),('float','rot[3]'),('ListBase','modifiers')]+([] if modern else [('float','obmat[4][4]')]),
      'CollectionObject':[('CollectionObject','*next'),('CollectionObject','*prev'),('Object','*ob')],
      'Collection':[('ListBase','gobject'),('ListBase','children')],
      'CollectionChild':[('CollectionChild','*next'),('Collection','*collection')],
      'Scene':[('Collection','*master_collection')],
      'FileGlobal':[('Scene','*curscene')],
    }
    primitive={'char':1,'short':2,'int':4,'float':4,'int64_t':8,'void':0}
    types=list(primitive)+list(schema); names=list(dict.fromkeys(n for fields in schema.values() for _,n in fields))
    sizes=dict(primitive); layouts={}
    def layout(name):
        if name in sizes: return sizes[name]
        offset=0; fields={}
        for t,decl in schema[name]:
            count=1
            for n in re.findall(r'\[(\d+)\]',decl): count*=int(n)
            size=(8 if '*' in decl else layout(t))*count
            field=re.search(r'\w+',decl).group(); fields[field]=(t,decl,count,offset,size); offset+=size
        sizes[name]=offset; layouts[name]=fields; return offset
    for name in schema: layout(name)
    def pack_record(name,values):
        data=bytearray(sizes[name])
        for field,value in values.items():
            t,decl,count,offset,size=layouts[name][field]
            if isinstance(value,dict): raw=pack_record(t,value)
            elif isinstance(value,bytes): raw=value
            else:
                code='Q' if '*' in decl else {'char':'b','short':'h','int':'i','float':'f','int64_t':'q'}[t]
                raw=struct.pack('<'+code*count,*(value if isinstance(value,(tuple,list)) else [value]))
            assert len(raw)==size,(name,field,len(raw),size)
            data[offset:offset+size]=raw
        return bytes(data)
    blocks=[]
    def block(code,address,type_name,data,count=1): blocks.append((code,address,list(schema).index(type_name) if type_name else 0,data,count))
    identity=(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)
    points=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    block(b'DATA',0x1000,'MVert',b''.join(pack_record('MVert',{'co':p}) for p in points),8)
    block(b'DATA',0x2000,'MPoly',b''.join(pack_record('MPoly',{'loopstart':i*4,'totloop':4,'mat_nr':i%2 if material_slots else 0}) for i in range(6)),6)
    block(b'DATA',0x3000,'MLoop',b''.join(pack_record('MLoop',{'v':v,'e':0}) for face in faces for v in face),24)
    mesh={'id':{'lib':1 if library else 0},'totvert':8,'totpoly':6,'totloop':24,'mvert':0x1000,'mpoly':0x2000,'mloop':0x3000}
    if material_slots:
        mesh.update(totcol=2,mat=0x17000)
        block(b'MA\0\0',0x15000,'Material',pack_record('Material',{'r':1,'g':0,'b':0,'roughness':.5}))
        block(b'MA\0\0',0x16000,'Material',pack_record('Material',{'r':0,'g':0,'b':1,'roughness':.5}))
        block(b'DATA',0x17000,None,struct.pack('<QQ',0x15000,0x16000))
    if attributes:
        mesh.update(mvert=0,mpoly=0,mloop=0,poly_offset_indices=0x4000,attribute_storage={'dna_attributes':0x5000,'dna_attributes_num':2})
        block(b'DATA',0x4000,None,struct.pack('<7i',*range(0,25,4)))
        block(b'DATA',0x6000,None,b'position\0')
        block(b'DATA',0x7000,None,b'.corner_vert\0')
        block(b'DATA',0x8000,None,struct.pack('<24i',*(v for face in faces for v in face)))
        block(b'DATA',0x9000,'AttributeArray',pack_record('AttributeArray',{'data':0x1000,'size':8}))
        block(b'DATA',0xa000,'AttributeArray',pack_record('AttributeArray',{'data':0x8000,'size':24}))
        block(b'DATA',0x5000,'Attribute',pack_record('Attribute',{'name':0x6000,'data':0x9000})+pack_record('Attribute',{'name':0x7000,'data':0xa000}),2)
    block(b'ME\0\0',0xb000,'Mesh',pack_record('Mesh',mesh))
    if subdivision:
        block(b'DATA',0x18000,'SubsurfModifierData',pack_record('SubsurfModifierData',{'modifier':{'type':1,'mode':1 if viewport else 2},'levels':subdivision,'renderLevels':1}))
    for i in range(2):
        obj={'type':1,'rotmode':1,'data':0xb000,'loc':(i*4,0,0),'size':(1,1,1),'dscale':(1,1,1),'parentinv':identity}
        if parented:
            if i==0: obj.update(loc=(2,0,0),size=(2,1,1),rot=(0,0,1.5707963267948966))
            else: obj['parent']=0xc000
        if subdivision: obj['modifiers']={'first':0x18000,'last':0x18000}
        if not modern: obj['obmat']=identity[:12]+(i*4,0,0,1)
        block(b'OB\0\0',0xc000+i*0x1000,'Object',pack_record('Object',obj))
    block(b'DATA',0xe000,'CollectionObject',pack_record('CollectionObject',{'next':0xf000,'ob':0xc000}))
    block(b'DATA',0xf000,'CollectionObject',pack_record('CollectionObject',{'prev':0xe000,'ob':0xd000}))
    block(b'GR\0\0',0x10000,'Collection',pack_record('Collection',{'gobject':{'first':0xe000,'last':0xf000},'children':{}}))
    block(b'SC\0\0',0x11000,'Scene',pack_record('Scene',{'master_collection':0x10000}))
    block(b'GLOB',0x12000,'FileGlobal',pack_record('FileGlobal',{'curscene':0x11000}))
    def pad(data): return data+b'\0'*((-len(data))%4)
    dna=b'SDNANAME'+struct.pack('<I',len(names))+pad(b''.join(n.encode()+b'\0' for n in names))
    dna+=b'TYPE'+struct.pack('<I',len(types))+pad(b''.join(t.encode()+b'\0' for t in types))
    dna+=b'TLEN'+pad(struct.pack('<'+'H'*len(types),*(sizes[t] for t in types)))
    dna+=b'STRC'+struct.pack('<I',len(schema))
    for t,fields in schema.items():
        dna+=struct.pack('<HH',types.index(t),len(fields))
        for field_type,decl in fields: dna+=struct.pack('<HH',types.index(field_type),names.index(decl))
    block(b'DNA1',0x13000,None,dna)
    raw=b'BLENDER17-01v0501' if modern else b'BLENDER-v280'
    for code,address,dna,data,count in blocks+[(b'ENDB',0,0,b'',0)]:
        header=struct.pack('<4s4xQQII',code,address,len(data),dna,count) if modern else struct.pack('<4sIQII',code,len(data),address,dna,count)
        raw+=header+data
    path.write_bytes(raw)
    return raw
