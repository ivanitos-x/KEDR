"""Bounded compiler for domain operations, never for user-supplied shader code."""
import math
from ..contracts import AssetFailure

VERTEX='''attribute vec3 position; attribute vec3 normal; attribute vec3 texcoord;
uniform mat4 mvp; uniform mat4 rotation; uniform float modelZoom; varying vec3 N; varying vec3 generated; varying vec3 P;
void main(){ gl_Position=mvp*vec4(position,1.0); N=(rotation*vec4(normal,0.0)).xyz; generated=texcoord; P=(rotation*vec4(position*modelZoom,1.0)).xyz; }
'''

LIBRARY='''
varying vec3 N; varying vec3 generated;
float hash3(vec3 p){ return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453); }
float clap_noise3(vec3 p){
 vec3 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
 return mix(mix(mix(hash3(i),hash3(i+vec3(1,0,0)),f.x),mix(hash3(i+vec3(0,1,0)),hash3(i+vec3(1,1,0)),f.x),f.y),
 mix(mix(hash3(i+vec3(0,0,1)),hash3(i+vec3(1,0,1)),f.x),mix(hash3(i+vec3(0,1,1)),hash3(i+vec3(1,1,1)),f.x),f.y),f.z);
}
float fbm(vec3 p,float detail,float rough,float lac){
 float value=0.0,total=0.0,amplitude=1.0;
 for(int i=0;i<9;i++){
  float weight=clamp(detail-float(i)+1.0,0.0,1.0)*amplitude;
  value+=clap_noise3(p)*weight; total+=weight; p*=clamp(lac,0.01,10.0); amplitude*=clamp(rough,0.0,1.0);
 }
 return value/max(total,0.0001);
}
vec4 noise_node(vec3 p,float scale,float detail,float rough,float lac,float distortion){
 p*=scale;
 if(abs(distortion)>0.00001) p+=(vec3(clap_noise3(p),clap_noise3(p+vec3(19)),clap_noise3(p+vec3(37)))-0.5)*distortion;
 float f=fbm(p,clamp(detail,0.0,8.0),rough,lac);
 return vec4(f,fbm(p+vec3(19.1,7.7,3.3),clamp(detail,0.0,8.0),rough,lac),fbm(p+vec3(5.2,31.7,9.1),clamp(detail,0.0,8.0),rough,lac),f);
}
vec3 mapping(vec3 p,vec3 t,vec3 r,vec3 s){
 p*=s;
 p=vec3(p.x,p.y*cos(r.x)-p.z*sin(r.x),p.y*sin(r.x)+p.z*cos(r.x));
 p=vec3(p.x*cos(r.y)+p.z*sin(r.y),p.y,-p.x*sin(r.y)+p.z*cos(r.y));
 p=vec3(p.x*cos(r.z)-p.y*sin(r.z),p.x*sin(r.z)+p.y*cos(r.z),p.z);
 return p+t;
}
'''

def number(value):
    if not math.isfinite(value) or abs(value)>1e6: raise AssetFailure('invalid_input','CLAP-RENDER-005','Некорректное число в материале')
    text=format(value,'.9g')
    return text if '.' in text or 'e' in text.lower() else text+'.0'

def fragment_shader(material,lighting_source=None):
    if len(material.nodes)>256: raise AssetFailure('invalid_input','CLAP-RENDER-004','Слишком сложный материал')
    functions=[]; lines=[]
    def vec(values):
        if len(values)!=4: raise ValueError('Expected RGBA constant')
        return 'vec4('+','.join(number(v) for v in values)+')'
    for i,node in enumerate(material.nodes):
        if any(type(k)!=int or not 0<=k<i for k in node.inputs): raise ValueError('Invalid material graph order')
        args=['n'+str(k) for k in node.inputs]; values=node.values; op=node.operation
        if op=='constant': expression=vec(values)
        elif op=='texture' and material.texture is not None:
            lines.append(f'vec4 tex{i}=texture2D(base_color_texture,generated.xy);')
            if material.texture.has_alpha: lines.append(f'if(tex{i}.a<0.5) discard;')
            expression=f'vec4(pow(tex{i}.rgb,vec3(2.2)),1.0)'
        elif op=='generated': expression='vec4(generated,1.0)'
        elif op=='object': expression='vec4(generated*2.0-1.0,1.0)'
        elif op=='mapping': expression=f'vec4(mapping({args[0]}.xyz,{args[1]}.xyz,{args[2]}.xyz,{args[3]}.xyz),1.0)'
        elif op=='noise': expression=f'noise_node({args[0]}.xyz,'+','.join(a+'.x' for a in args[1:])+')'
        elif op=='noise_fac': expression=f'vec4({args[0]}.a)'
        elif op=='noise_color': expression=f'vec4({args[0]}.rgb,1.0)'
        elif op=='luminance': expression=f'vec4(dot({args[0]}.rgb,vec3(0.2126,0.7152,0.0722)))'
        elif op=='ramp':
            interpolation=int(values[0]); points=[values[j:j+5] for j in range(1,len(values),5)]
            if not 1<=len(points)<=32 or any(len(p)!=5 for p in points): raise ValueError('Invalid color ramp')
            body=f'vec4 ramp{i}(float x){{ if(x<={number(points[0][0])}) return {vec(points[0][1:])};'
            for a,b in zip(points,points[1:]):
                factor=f'clamp((x-{number(a[0])})/{number(max(b[0]-a[0],1e-9))},0.0,1.0)'
                if interpolation==1: factor=f'smoothstep(0.0,1.0,{factor})'
                blend=vec(a[1:]) if interpolation==4 else f'mix({vec(a[1:])},{vec(b[1:])},{factor})'
                body+=f'if(x<{number(b[0])}) return {blend};'
            functions.append(body+f'return {vec(points[-1][1:])};}}')
            expression=f'ramp{i}({args[0]}.x)'
        elif op=='mix':
            factor=f'clamp({args[0]}.x,0.0,1.0)' if values[1] else args[0]+'.x'
            a,b=args[1]+'.rgb',args[2]+'.rgb'; mode=int(values[0])
            expressions={0:b,1:f'({a}+{b})',2:f'({a}*{b})',3:f'({a}-{b})',4:f'(1.0-(1.0-{a})*(1.0-{b}))',6:f'abs({a}-{b})',7:f'min({a},{b})',8:f'max({a},{b})'}
            expression=f'vec4(mix({a},{expressions[mode]},{factor}),1.0)'
            if values[2]: expression=f'clamp({expression},0.0,1.0)'
        else: raise AssetFailure('unsupported','CLAP-RENDER-005','Неподдерживаемая операция материала')
        lines.append(f'vec4 n{i}={expression};')
    for index in (material.color,material.roughness,material.metallic):
        if not 0<=index<len(material.nodes): raise ValueError('Invalid material output')
    lighting=f'''
 vec3 base=max(n{material.color}.rgb,vec3(0.0));
 float rough=clamp(n{material.roughness}.x,0.04,1.0),metal=clamp(n{material.metallic}.x,0.0,1.0);
 vec3 normal=normalize(N); if(normal.z<0.0) normal=-normal;
 vec3 light=normalize(vec3(-0.4,0.7,1.0));
 float diffuse=0.28+0.72*max(dot(normal,light),0.0);
 float spec=pow(max(dot(normal,normalize(light+vec3(0,0,1))),0.0),mix(128.0,4.0,rough));
 vec3 color=base*diffuse*(1.0-0.35*metal)+mix(vec3(0.04),base,metal)*spec*(1.0-0.65*rough);
 gl_FragColor=vec4(pow(clamp(color,0.0,1.0),vec3(1.0/2.2)),1.0);
'''
    extra,lighting=lighting_source(material) if lighting_source is not None else ('',lighting)
    sampler='uniform sampler2D base_color_texture;\n' if material.texture is not None else ''
    result=LIBRARY+sampler+extra+'\n'.join(functions)+'\nvoid main(){'+'\n'.join(lines)+lighting+'}'
    if len(result)>65536: raise AssetFailure('invalid_input','CLAP-RENDER-004','Превышен бюджет shader материала')
    return result
