"""Reviewed static car graph primitives. No claim of live-road or turn-aware validity."""
from __future__ import annotations
import re
import numpy as np
from scipy import sparse

SPEED={'motorway':80,'motorway_link':40,'trunk':60,'trunk_link':40,'primary':50,'primary_link':40,'secondary':50,'secondary_link':40,'tertiary':40,'tertiary_link':30,'unclassified':30,'residential':30,'living_street':15,'service':15,'road':20}
DENIED={'no','private'}
ALLOWED={'yes','designated','permissive','destination','customers','delivery'}

def access_value(tags):
    """Specific motorcar > motor_vehicle > vehicle > general access."""
    for key in ('motorcar','motor_vehicle','vehicle','access'):
        value=tags.get(key)
        if value is not None:return str(value).strip().lower(),key
    return None,None

def permitted(tags):
    value,key=access_value(tags)
    return value is None or value in ALLOWED

def direction(tags):
    """Return original-node-order direction; None is unsupported reversible/unknown."""
    raw=next((tags.get(k) for k in ('oneway:motorcar','oneway:motor_vehicle','oneway') if tags.get(k) is not None),None)
    if raw is not None:
        raw=str(raw).strip().lower()
        if raw in ('yes','1','true'):return 1
        if raw in ('-1','reverse'):return -1
        if raw in ('no','0','false'):return 0
        return None
    return 1 if tags.get('highway')=='motorway' or tags.get('junction')=='roundabout' else 0

def speed_limit(raw):
    if raw is None:return None
    text=str(raw).strip().lower()
    if text=='walk':return 5.0
    m=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?',text)
    if not m:return None
    value=float(m[1])*(1.609344 if m[2]=='mph' else 1.0)
    return value

def directional_speeds(tags):
    base=float(SPEED[tags['highway']]);general=speed_limit(tags.get('maxspeed'))
    general=min(base,general) if general is not None else base
    forward=speed_limit(tags.get('maxspeed:forward'));backward=speed_limit(tags.get('maxspeed:backward'))
    return min(general,forward) if forward is not None else general,min(general,backward) if backward is not None else general

def minimum_arc_csr(rows,cols,weights,n):
    """Parallel alternatives aggregate by minimum, never CSR's default sum."""
    rows=np.asarray(rows,dtype=np.int64);cols=np.asarray(cols,dtype=np.int64);weights=np.asarray(weights,dtype=float)
    if not(len(rows)==len(cols)==len(weights)):raise ValueError('Arc lengths differ')
    if len(rows)==0:return sparse.csr_matrix((n,n),dtype=float)
    if rows.min()<0 or cols.min()<0 or rows.max()>=n or cols.max()>=n:raise ValueError('Node index out of range')
    if not np.isfinite(weights).all() or (weights<=0).any():raise ValueError('Arc weights must be finite positive')
    order=np.lexsort((cols,rows));r=rows[order];c=cols[order];w=weights[order]
    starts=np.r_[0,np.nonzero((r[1:]!=r[:-1])|(c[1:]!=c[:-1]))[0]+1]
    return sparse.csr_matrix((np.minimum.reduceat(w,starts),(r[starts],c[starts])),shape=(n,n))

def directed_time_csr(z,top_speed=40.,speed_factor=.9):
    if not(0<speed_factor<=1 and top_speed>0):raise ValueError('Invalid scenario speed')
    u,v,ow=z['u'],z['v'],z['oneway'];fw=ow>=0;bw=ow<=0
    tf=z['length_m']/(np.minimum(z['speed_forward_kmh'],top_speed)*speed_factor/3.6)
    tb=z['length_m']/(np.minimum(z['speed_backward_kmh'],top_speed)*speed_factor/3.6)
    return minimum_arc_csr(np.r_[u[fw],v[bw]],np.r_[v[fw],u[bw]],np.maximum(np.r_[tf[fw],tb[bw]],.01),len(z['node_osm_id']))
