"""GGX/height-correlated Smith/Schlick BRDF, linear HDR studio and tone mapping."""
LIBRARY='''
varying vec3 P;
uniform int has_environment; uniform sampler2D hdr_environment; uniform vec2 environment_size;
const float PI=3.141592653589793;
vec3 fresnel(float vh,vec3 f0){ return f0+(1.0-f0)*pow(clamp(1.0-vh,0.0,1.0),5.0); }
float distribution(float nh,float alpha){ float aa=alpha*alpha; float d=nh*nh*(aa-1.0)+1.0; return aa/max(PI*d*d,0.0000001); }
float visibility(float nv,float nl,float alpha){
 float aa=alpha*alpha;
 return 0.5/max(nl*sqrt(nv*nv*(1.0-aa)+aa)+nv*sqrt(nl*nl*(1.0-aa)+aa),0.000001);
}
vec3 brdf_light(vec3 N,vec3 V,vec3 L,vec3 radiance,vec3 base,float metal,float alpha){
 vec3 H=normalize(V+L); float nv=max(dot(N,V),0.0001),nl=max(dot(N,L),0.0),nh=max(dot(N,H),0.0),vh=max(dot(V,H),0.0);
 vec3 F=fresnel(vh,mix(vec3(0.04),base,metal));
 vec3 diffuse=(1.0-metal)*(1.0-F)*base/PI;
 return (diffuse+distribution(nh,alpha)*visibility(nv,nl,alpha)*F)*radiance*nl;
}
vec3 decode_rgbe(vec4 c){ return c.a<0.001?vec3(0):min(c.rgb*(255.0/256.0)*exp2(min(c.a*255.0-128.0,120.0)),vec3(65504.0)); }
vec3 hdr_pixel(vec2 p){
 return decode_rgbe(texture2D(hdr_environment,vec2(fract((p.x+0.5)/environment_size.x),(clamp(p.y,0.0,environment_size.y-1.0)+0.5)/environment_size.y)));
}
vec3 environment(vec3 d){
 if(has_environment!=0){
  vec2 uv=vec2(atan(d.z,d.x)/(2.0*PI)+0.5,0.5-asin(clamp(d.y,-1.0,1.0))/PI);
  vec2 p=uv*environment_size-0.5,i=floor(p),f=fract(p);
  return mix(mix(hdr_pixel(i),hdr_pixel(i+vec2(1,0)),f.x),mix(hdr_pixel(i+vec2(0,1)),hdr_pixel(i+vec2(1,1)),f.x),f.y);
 }
 float sky=clamp(d.y*0.5+0.5,0.0,1.0);
 vec3 color=mix(vec3(0.055,0.045,0.035),vec3(0.3,0.39,0.55),sky);
 color+=vec3(7.0,6.5,5.7)*pow(max(dot(d,normalize(vec3(-0.8,0.9,0.7))),0.0),42.0);
 color+=vec3(2.0,2.5,3.5)*pow(max(dot(d,normalize(vec3(0.9,0.4,-0.4))),0.0),24.0);
 return color;
}
float radical_inverse(int index){
 float value=float(index),result=0.0,weight=0.5;
 for(int j=0;j<5;j++){ result+=mod(value,2.0)*weight; value=floor(value*0.5); weight*=0.5; }
 return result;
}
vec3 from_tangent(vec3 direction,vec3 N){
 // A pole-safe orthonormal frame; cross(up,N) spun radially at the view pole.
 float s=N.z>=0.0?1.0:-1.0,a=-1.0/(s+N.z),b=N.x*N.y*a;
 vec3 T=vec3(1.0+s*N.x*N.x*a,s*b,-s*N.x);
 vec3 B=vec3(b,s+N.y*N.y*a,-N.y);
 return normalize(T*direction.x+B*direction.y+N*direction.z);
}
vec3 ibl(vec3 N,vec3 V,vec3 base,float metal,float alpha){
 vec3 f0=mix(vec3(0.04),base,metal); float nv=max(dot(N,V),0.0001);
 vec3 diffuse=vec3(0),specular=vec3(0);
 for(int i=0;i<16;i++){
  float u=(float(i)+0.5)/16.0,v=radical_inverse(i),phi=2.0*PI*u;
  vec3 D=from_tangent(vec3(sqrt(v)*cos(phi),sqrt(v)*sin(phi),sqrt(1.0-v)),N);
  diffuse+=environment(D);
  float ct=sqrt((1.0-v)/(1.0+(alpha*alpha-1.0)*v)),st=sqrt(max(0.0,1.0-ct*ct));
  vec3 H=from_tangent(vec3(st*cos(phi),st*sin(phi),ct),N); vec3 L=reflect(-V,H);
  float nl=max(dot(N,L),0.0),nh=max(dot(N,H),0.0001),vh=max(dot(V,H),0.0);
  if(nl>0.0) specular+=environment(L)*fresnel(vh,f0)*(4.0*visibility(nv,nl,alpha)*nl*vh/max(nh,0.0001));
 }
 vec3 kd=(1.0-metal)*(1.0-fresnel(nv,f0));
 return kd*base*diffuse/16.0+specular/16.0;
}
vec3 tone_map(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
vec3 encode_srgb(vec3 x){ return mix(12.92*x,1.055*pow(max(x,vec3(0)),vec3(1.0/2.4))-0.055,step(vec3(0.0031308),x)); }
'''

def lighting_source(material):
    return LIBRARY,f'''
 vec3 base=clamp(n{material.color}.rgb,0.0,1.0);
 float rough=clamp(n{material.roughness}.x,0.045,1.0),metal=clamp(n{material.metallic}.x,0.0,1.0),alpha=rough*rough;
 vec3 V=normalize(vec3(0,0,3.5)-P),normal=normalize(N); if(dot(normal,V)<0.0) normal=-normal;
 vec3 color=brdf_light(normal,V,normalize(vec3(-0.5,0.8,1)),vec3(2.4,2.2,1.9),base,metal,alpha);
 color+=brdf_light(normal,V,normalize(vec3(0.9,0.2,0.5)),vec3(0.45,0.6,0.9),base,metal,alpha);
 color+=ibl(normal,V,base,metal,alpha);
 gl_FragColor=vec4(encode_srgb(tone_map(max(color,vec3(0)))),1.0);
'''
