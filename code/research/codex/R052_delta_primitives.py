"""Frozen-policy primitives for additional origins; not a new road scenario."""
from pathlib import Path
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse.csgraph import dijkstra
from graph_integrity import directed_time_csr

def sphere(lat,lon):
    a=np.radians(np.asarray(lat,dtype=float));b=np.radians(np.asarray(lon,dtype=float))
    return np.c_[np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)]
def arc(chord):return 2*6371000*np.arcsin(np.clip(np.asarray(chord,dtype=float)/2,0,1))
def center(code):
    c=str(code);h=int(c[8])
    la=int(c[:2])/1.5+int(c[4])*5/60+int(c[6])*30/3600+(h in (3,4))*15/3600+7.5/3600
    lo=int(c[2:4])+100+int(c[5])*7.5/60+int(c[7])*45/3600+(h in (2,4))*22.5/3600+11.25/3600
    return la,lo

def geometry(pop,code):
    D=pop[pop.pref_code.eq(code)]
    geom=pop.groupby('MESH_ID',as_index=False).agg(lat=('lat','mean'),lon=('lon','mean'))
    bounds=(D.lon.min(),D.lon.max(),D.lat.min(),D.lat.max())
    a,b,c,d=bounds
    G=geom[geom.lon.between(a-.55,b+.55)&geom.lat.between(c-.55,d+.55)].reset_index(drop=True)
    G['in_pilot']=G.MESH_ID.isin(D.MESH_ID)
    return G,bounds

def clipped_graph(z,bounds,prefix_path):
    a,b,c,d=bounds;lat=z['node_lat'];lon=z['node_lon'];u=z['u'];v=z['v']
    inside=(lon>=a-.65)&(lon<=b+.65)&(lat>=c-.65)&(lat<=d+.65)
    keep=inside[u]&inside[v];p=Path(prefix_path);assert not p.exists()
    prefix=np.lib.format.open_memmap(p,mode='w+',dtype=np.int64,shape=inside.shape)
    np.cumsum(inside,out=prefix)
    for i in range(0,len(prefix),65536):np.subtract(prefix[i:i+65536],1,out=prefix[i:i+65536])
    prefix.flush()
    C={'u':np.asarray(prefix[u[keep]]),'v':np.asarray(prefix[v[keep]]),'node_lat':np.asarray(lat[inside]),'node_lon':np.asarray(lon[inside])}
    for k in ['length_m','speed_forward_kmh','speed_backward_kmh','oneway','limited_access']:C[k]=np.asarray(z[k][keep])
    n=len(C['node_lat']);C['node_osm_id']=range(n)
    graph=directed_time_csr(C,40.,.9)
    deg=np.bincount(np.r_[C['u'],C['v']],minlength=n);fast=C['limited_access'].astype(bool)
    limited=np.bincount(np.r_[C['u'][fast],C['v'][fast]],minlength=n)
    allowed=np.flatnonzero((deg>0)&(limited<deg))
    tree=cKDTree(sphere(C['node_lat'][allowed],C['node_lon'][allowed]))
    return graph,tree,allowed,{'nodes':n,'segments':len(C['u']),'arcs':int(graph.nnz)}

def snap(tree,allowed,lat,lon):
    chord,idx=tree.query(sphere(lat,lon));return allowed[idx],arc(chord)

def edges(graph,src,dist_o,target,dist_g,valid_o,valid_g):
    road=dijkstra(graph,directed=True,indices=src,limit=3600)
    T=road[:,target]+(dist_o[:,None]+dist_g[None,:])/(15/3.6)
    T[~valid_o,:]=np.inf;T[:,~valid_g]=np.inf
    parts=[]
    for k in range(len(src)):
        g=np.flatnonzero(np.isfinite(T[k])&(T[k]<=3600));t=(T[k,g]/60).astype(np.float32)
        parts.append(pd.DataFrame({'g':g.astype(np.int32),'o':np.full(len(g),k,np.int32),'band':(np.ceil(t/5)*5).clip(5,60).astype(np.uint8),'t_exact':t}))
    return pd.concat(parts,ignore_index=True)
