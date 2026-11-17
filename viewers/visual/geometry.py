"""Shared scene construction, independent of loaders, Qt and renderer."""
import math
from array import array
from .contracts import SceneData, AssetFailure, Triangle

def triangles_to_scene(triangles,info,context):
    vertices=array('f'); coordinates=array('f'); material_ids=[]; low=[math.inf]*3; high=[-math.inf]*3; count=0
    for triangle in triangles:
        abc=triangle.positions if isinstance(triangle,Triangle) else triangle
        if isinstance(triangle,Triangle):
            material_ids.append(triangle.material)
            for coordinate in triangle.coordinates: coordinates.extend(coordinate)
        if count%256==0: context.check()
        count+=1
        if count>200000: raise AssetFailure('invalid_input','CLAP-RENDER-004','Лимит — 200000 треугольников')
        a,b,c=abc; u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in n)); n=[x/length for x in n] if length>1e-20 else [0,0,1]
        for vertex_index,p in enumerate(abc):
            if any(not math.isfinite(x) or abs(x)>1e15 for x in p): raise AssetFailure('invalid_input','CLAP-RENDER-001','Некорректные координаты')
            for i,x in enumerate(p): low[i]=min(low[i],x); high[i]=max(high[i],x)
            normal=triangle.normals[vertex_index] if isinstance(triangle,Triangle) and triangle.normals else n
            vertices.extend((*p,*normal))
    radius=math.sqrt(sum((b-a)**2 for a,b in zip(low,high)))/2
    if not count or radius<1e-12: raise AssetFailure('invalid_input','CLAP-RENDER-001','Нет отображаемой геометрии')
    center=[(a+b)/2 for a,b in zip(low,high)]
    for i in range(0,len(vertices),6):
        for k in range(3): vertices[i+k]=(vertices[i+k]-center[k])/radius
    return SceneData(vertices.tobytes(),dict(info,triangles=count),material_ids=tuple(material_ids),coordinates=coordinates.tobytes())

def triangulate(points,context):
    """Ear clipping for simple planar polygons, bounded to 1024 corners."""
    n=len(points)
    if n<3 or n>1024: raise AssetFailure('unsupported','CLAP-RENDER-005','Полигон должен иметь 3–1024 вершины')
    if n==3: return [(0,1,2)]
    normal=[sum((points[i][(k+1)%3]-points[(i+1)%n][(k+1)%3])*(points[i][(k+2)%3]+points[(i+1)%n][(k+2)%3]) for i in range(n)) for k in range(3)]
    drop=max(range(3),key=lambda k:abs(normal[k])); axes=[k for k in range(3) if k!=drop]
    xy=[(p[axes[0]],p[axes[1]]) for p in points]
    area=sum(xy[i][0]*xy[(i+1)%n][1]-xy[(i+1)%n][0]*xy[i][1] for i in range(n)); direction=1 if area>=0 else -1
    def cross(a,b,c): return direction*((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
    # Real edit meshes may retain distinct corner IDs at identical positions.
    # Remove zero-length edges before clipping, retaining original vertex IDs.
    extent=max(max(p[k] for p in xy)-min(p[k] for p in xy) for k in range(2))
    epsilon=max(extent*1e-9,1e-15)
    pending=[]
    for i in range(n):
        if not pending or sum((xy[i][k]-xy[pending[-1]][k])**2 for k in range(2))>epsilon**2: pending.append(i)
    if len(pending)>1 and sum((xy[pending[0]][k]-xy[pending[-1]][k])**2 for k in range(2))<=epsilon**2: pending.pop()
    if len(pending)<3: raise AssetFailure('unsupported','CLAP-RENDER-005','Вырожденная грань после удаления нулевых рёбер')
    result=[]; operations=0
    while len(pending)>3:
        context.check(); found=False
        for i,b in enumerate(pending):
            a=pending[i-1]; c=pending[(i+1)%len(pending)]
            if cross(xy[a],xy[b],xy[c])<=1e-14: continue
            inside=False
            for p in pending:
                operations+=1
                if operations>2_000_000: raise AssetFailure('failed','CLAP-RENDER-004','Слишком сложный полигон')
                if p not in (a,b,c) and min(cross(xy[a],xy[b],xy[p]),cross(xy[b],xy[c],xy[p]),cross(xy[c],xy[a],xy[p]))>=-1e-14: inside=True; break
            if not inside:
                result.append((a,b,c)); pending.pop(i); found=True; break
        if not found: raise AssetFailure('unsupported','CLAP-RENDER-005','Самопересекающийся или вырожденный полигон')
    result.append(tuple(pending)); return result
