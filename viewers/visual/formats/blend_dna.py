"""Read-only SDNA container. Pointers are file addresses, never native pointers.

No bpy, subprocess, drivers, linked libraries, paths or embedded Python are evaluated.
"""
import bisect
import gzip
import io
import re
import struct
import time
from dataclasses import dataclass
from ..contracts import AssetFailure

MAX_FILE=128*1024*1024

def invalid(reason): return AssetFailure('invalid_input','CLAP-RENDER-001',reason)

def read_bytes(path,context):
    with path.open('rb') as source:
        magic=source.read(4); source.seek(0)
        if magic[:2]==b'\x1f\x8b': stream=gzip.GzipFile(fileobj=source)
        elif magic==b'\x28\xb5\x2f\xfd':
            try: import zstandard
            except ImportError as exc: raise AssetFailure('unavailable','CLAP-RENDER-006','Для сжатого .blend установите zstandard из requirements.txt') from exc
            stream=zstandard.ZstdDecompressor(max_window_size=MAX_FILE).stream_reader(source)
        else: stream=source
        try:
            chunks=[]; total=0
            while True:
                context.check()
                chunk=stream.read(min(1024*1024,MAX_FILE+1-total))
                if not chunk: break
                total+=len(chunk)
                if total>MAX_FILE: raise AssetFailure('invalid_input','CLAP-RENDER-004','Распакованный .blend превышает 128 MiB')
                chunks.append(chunk)
            return b''.join(chunks)
        finally:
            if stream is not source: stream.close()

@dataclass(frozen=True)
class Field:
    type: str
    offset: int
    count: int
    pointer: bool
    size: int

class Record:
    def __init__(self,file,type_name,data): self.file,self.type,self.data=file,type_name,data
    def has(self,name): return name in self.file.fields[self.type]
    def get(self,name,default=None):
        field=self.file.fields[self.type].get(name)
        if field is None: return default
        raw=self.data[field.offset:field.offset+field.size]
        if len(raw)!=field.size: raise invalid('Усечённая SDNA-структура '+self.type)
        if field.pointer:
            values=struct.unpack(self.file.endian+('Q' if self.file.pointer==8 else 'I')*field.count,raw)
        elif field.type in self.file.fields:
            if field.count!=1: return [Record(self.file,field.type,raw[i*self.file.sizes[field.type]:(i+1)*self.file.sizes[field.type]]) for i in range(field.count)]
            return Record(self.file,field.type,raw)
        elif field.type in ('char','uchar','unsigned char'):
            return bytes(raw).split(b'\x00',1)[0].decode('utf-8',errors='replace') if field.count>1 else raw[0]
        else:
            code={'short':'h','ushort':'H','unsigned short':'H','int':'i','uint':'I','unsigned int':'I','float':'f','double':'d','int64_t':'q','uint64_t':'Q','int8_t':'b','uint8_t':'B','int16_t':'h','uint16_t':'H','int32_t':'i','uint32_t':'I'}.get(field.type)
            if code is None: raise invalid('Неподдерживаемый SDNA-тип '+field.type)
            values=struct.unpack(self.file.endian+code*field.count,raw)
        return values[0] if field.count==1 else values

class BlendFile:
    def __init__(self,raw,context):
        self.raw=raw; self.context=context; self.deadline=time.monotonic()+context.timeout
        if raw[:7]!=b'BLENDER': raise invalid('Неверная сигнатура .blend')
        if raw[7:9]==b'17':
            if raw[9:13]!=b'-01v': raise invalid('Неизвестная версия контейнера .blend')
            self.pointer=8; self.endian='<'; offset=17; fmt='<4s4xQQII'; self.version=raw[13:17].decode('ascii')
            modern=True
        else:
            if raw[7:8] not in (b'-',b'_') or raw[8:9] not in (b'v',b'V'): raise invalid('Неверный заголовок .blend')
            self.pointer=8 if raw[7:8]==b'-' else 4; self.endian='<' if raw[8:9]==b'v' else '>'
            offset=12; fmt=self.endian+'4sI'+('Q' if self.pointer==8 else 'I')+'II'; self.version=raw[9:12].decode('ascii'); modern=False
        self.blocks=[]; self.by_address={}; self.ambiguous=set(); dna=None; ended=False; size=struct.calcsize(fmt)
        while offset<len(raw):
            self.check()
            if len(self.blocks)>100000: raise invalid('Слишком много блоков .blend')
            if offset+size>len(raw): raise invalid('Оборванный заголовок блока')
            values=struct.unpack_from(fmt,raw,offset); offset+=size
            code,address,length,sdna,count=values if modern else (values[0],values[2],values[1],values[3],values[4])
            if offset+length>len(raw): raise invalid('Блок выходит за границы .blend')
            data=memoryview(raw)[offset:offset+length]; offset+=length
            if code==b'ENDB': ended=True; break
            if code==b'DNA1': dna=bytes(data)
            block=(code,address,sdna,count,data)
            self.blocks.append(block)
            if address and length and code not in (b'REND',b'TEST',b'GLOB',b'DNA1'):
                # DATA addresses are scoped to owning IDs in Blender. Unrelated
                # properties may reuse an address; reject only an ambiguous
                # address actually requested by the geometry reader.
                prior=self.by_address.get(address)
                if prior is not None:
                    if prior[2:]!=block[2:]: self.ambiguous.add(address)
                else: self.by_address[address]=block
        if not ended or dna is None: raise invalid('Отсутствует ENDB / DNA1')
        self.modern=modern
        self.addresses=sorted(self.by_address)
        self.parse_dna(dna)
    def check(self):
        self.context.check()
        if time.monotonic()>self.deadline: raise AssetFailure('failed','CLAP-RENDER-008','Истёк бюджет чтения .blend')
    def parse_dna(self,data):
        pos=0
        def tag(value):
            nonlocal pos
            if data[pos:pos+4]!=value: raise invalid('Повреждена таблица SDNA')
            pos+=4
        def integer(code='I'):
            nonlocal pos
            result=struct.unpack_from(self.endian+code,data,pos)[0]; pos+=struct.calcsize(code); return result
        def strings():
            nonlocal pos
            count=integer()
            if count>100000: raise invalid('Чрезмерная SDNA')
            values=[]
            for _ in range(count):
                end=data.index(0,pos)
                if end-pos>1024: raise invalid('Чрезмерное имя SDNA')
                values.append(data[pos:end].decode('ascii')); pos=end+1
            pos=(pos+3)&~3
            return values
        tag(b'SDNA'); tag(b'NAME'); names=strings(); tag(b'TYPE'); types=strings(); tag(b'TLEN')
        sizes=[integer('H') for _ in types]; self.sizes=dict(zip(types,sizes)); pos=(pos+3)&~3
        tag(b'STRC'); count=integer()
        if count>20000: raise invalid('Чрезмерное число структур SDNA')
        self.fields={}; self.struct_names=[]
        for _ in range(count):
            self.check(); type_id=integer('H'); field_count=integer('H'); type_name=types[type_id]
            fields={}; offset=0
            for _ in range(field_count):
                type_index,name_index=integer('H'),integer('H'); declaration=names[name_index]
                dims=re.findall(r'\[(\d+)\]',declaration); num=1
                for dimension in dims: num*=int(dimension)
                pointer='*' in declaration
                length=(self.pointer if pointer else sizes[type_index])*num
                name=re.search(r'[A-Za-z_]\w*',declaration).group()
                fields[name]=Field(types[type_index],offset,num,pointer,length); offset+=length
            if offset!=sizes[type_id]: raise invalid('SDNA layout не совпадает: '+type_name)
            self.fields[type_name]=fields; self.struct_names.append(type_name)
    def bytes_at(self,address,size):
        if size<0 or size>MAX_FILE: raise invalid('Недопустимый размер массива')
        if address in self.ambiguous: raise invalid('Неоднозначный адрес геометрии .blend')
        if self.modern:
            block=self.by_address.get(address)
            if block is None or size>len(block[4]): raise invalid('Неразрешённый адрес или размер массива')
            return block[4][:size]
        pos=bisect.bisect_right(self.addresses,address)-1
        if pos<0: raise invalid('Неразрешённый адрес массива')
        start=self.addresses[pos]; block=self.by_address[start]; offset=address-start
        if start in self.ambiguous: raise invalid('Неоднозначный адрес геометрии .blend')
        if offset<0 or offset+size>len(block[4]): raise invalid('Массив выходит за блок .blend')
        return block[4][offset:offset+size]
    def records(self,address,type_name,count=1):
        if not 0<=count<=600000: raise invalid('Недопустимое число записей')
        size=self.sizes[type_name]; data=self.bytes_at(address,size*count)
        return [Record(self,type_name,data[i*size:(i+1)*size]) for i in range(count)]
    def typed_blocks(self,type_name):
        for _,_,dna,count,data in self.blocks:
            self.check()
            if dna<len(self.struct_names) and self.struct_names[dna]==type_name:
                size=self.sizes[type_name]
                if count*size>len(data) or count>10000: raise invalid('Размер SDNA-блока не совпадает')
                for i in range(count): yield Record(self,type_name,data[i*size:(i+1)*size])
