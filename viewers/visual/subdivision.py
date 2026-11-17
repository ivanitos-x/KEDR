"""Bounded polygon subdivision port; no file formats, Qt or Blender imports."""
import math
from dataclasses import replace
from .contracts import PolygonMesh,ModifiedMesh,AssetFailure

def average(points):
    return tuple(sum(p[k] for p in points)/len(points) for k in range(3))

class SubdivisionModifier:
    def __init__(self,triangle_budget=200000): self.triangle_budget=triangle_budget
    def apply(self,mesh,settings,context):
        if settings.algorithm not in ('catmull-clark','simple') or not 0<=settings.levels<=6:
            raise AssetFailure('unsupported','CLAP-RENDER-005','Поддерживаются Catmull–Clark/Simple, уровни 0–6')
        current=mesh; completed=0; notices=[]
        for level in range(settings.levels):
            context.check()
            next_faces=sum(len(face) for face in current.faces)
            if next_faces*2>self.triangle_budget or next_faces*4>600000:
                notices.append(f'Subdivision Surface: уровень {settings.levels} ограничен до {completed} по бюджету геометрии.')
                break
            context.progress(f'Subdivision Surface: уровень {level+1} из {settings.levels}…')
            current=self.step(current,settings,context); completed+=1
        if completed and settings.algorithm=='catmull-clark': current=replace(current,normals=tuple(smooth_normals(current,context)))
        return ModifiedMesh(current,completed,tuple(notices))

    def step(self,mesh,settings,context):
        positions=mesh.positions; faces=mesh.faces
        edges={}; vertex_faces=[[] for _ in positions]; vertex_edges=[[] for _ in positions]
        face_points=[]
        for fi,face in enumerate(faces):
            if fi%256==0: context.check()
            if len(face)<3 or len(face)>1024 or len(set(face))!=len(face) or any(not 0<=v<len(positions) for v in face):
                raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: неверная или вырожденная грань')
            face_points.append(average([positions[v] for v in face]))
            for i,v in enumerate(face):
                vertex_faces[v].append(fi)
                key=tuple(sorted((v,face[(i+1)%len(face)])))
                if key not in edges:
                    edges[key]=[]; vertex_edges[key[0]].append(key); vertex_edges[key[1]].append(key)
                edges[key].append(fi)
                if len(edges[key])>2: raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: non-manifold ребро, более двух граней')
        updated=[]
        for v,p in enumerate(positions):
            if v%256==0: context.check()
            linked=vertex_edges[v]; attached=vertex_faces[v]
            boundary=[key[0] if key[1]==v else key[1] for key in linked if len(edges[key])==1]
            if settings.algorithm=='simple' or not linked: value=p
            elif boundary:
                if len(boundary)!=2: raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: non-manifold граница')
                if settings.preserve_boundary_corners and len(attached)==1: value=p
                else: value=tuple((6*p[k]+sum(positions[n][k] for n in boundary))/8 for k in range(3))
            else:
                if len(attached)!=len(linked): raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: non-manifold вершина')
                # Connected face fan: reject bow-ties instead of averaging disjoint sheets.
                seen={attached[0]}
                while True:
                    more=set(seen)
                    for edge in linked:
                        if any(fi in seen for fi in edges[edge]): more.update(edges[edge])
                    if more==seen: break
                    seen=more
                if len(seen)!=len(attached): raise AssetFailure('unsupported','CLAP-RENDER-005','Subdivision: разорванный веер вершины')
                n=len(attached); fp=average([face_points[i] for i in attached]); rp=average([average([positions[a],positions[b]]) for a,b in linked])
                value=tuple((fp[k]+2*rp[k]+(n-3)*p[k])/n for k in range(3))
            updated.append(value)
        edge_indices={}
        for i,(edge,neighbors) in enumerate(edges.items()):
            if i%256==0: context.check()
            edge_indices[edge]=len(updated)
            points=[positions[edge[0]],positions[edge[1]]]
            if settings.algorithm=='catmull-clark' and len(neighbors)==2: points+=[face_points[f] for f in neighbors]
            updated.append(average(points))
        face_offset=len(updated); updated.extend(face_points)
        result=[]; materials=[]
        for fi,face in enumerate(faces):
            if fi%256==0: context.check()
            for i,v in enumerate(face):
                before=edge_indices[tuple(sorted((face[i-1],v)))]; after=edge_indices[tuple(sorted((v,face[(i+1)%len(face)])))]
                result.append((v,after,face_offset+fi,before)); materials.append(mesh.materials[fi])
        if len(updated)>600000: raise AssetFailure('invalid_input','CLAP-RENDER-004','Subdivision: превышен лимит вершин')
        return PolygonMesh(tuple(updated),tuple(result),tuple(materials))

def smooth_normals(mesh,context):
    totals=[[0.,0.,0.] for _ in mesh.positions]
    for fi,face in enumerate(mesh.faces):
        if fi%256==0: context.check()
        points=[mesh.positions[i] for i in face]
        normal=[sum((points[i][(k+1)%3]-points[(i+1)%len(points)][(k+1)%3])*(points[i][(k+2)%3]+points[(i+1)%len(points)][(k+2)%3]) for i in range(len(points))) for k in range(3)]
        for v in face:
            for k in range(3): totals[v][k]+=normal[k]
    result=[]
    for normal in totals:
        length=math.sqrt(sum(x*x for x in normal))
        result.append(tuple(x/length for x in normal) if length>1e-20 else (0,0,1))
    return result
