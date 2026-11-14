"""Merge reviewed graphs by road identity/version, preserving parallel alternatives."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,json,hashlib,time
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('inputs',nargs='+');args=ap.parse_args();out=Path(args.out)
if out.exists() or Path(str(out)+'.partial.npz').exists():raise FileExistsError('Choose a new merged output')
started=time.monotonic();paths=[Path(p) for p in args.inputs];metas=[json.loads(Path(str(p)+'.json').read_text(encoding='utf-8')) for p in paths]
order=sorted(range(len(paths)),key=lambda i:(metas[i].get('replication_timestamp',''),str(paths[i])),reverse=True);paths=[paths[i] for i in order];metas=[metas[i] for i in order];Z=[]
for p,m in zip(paths,metas):
 with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==m['graph_sha256']
 z=np.load(p);assert int(z['format_version'][0])==2;Z.append(z)
ids=np.concatenate([z['node_osm_id'] for z in Z]);lat=np.concatenate([z['node_lat'] for z in Z]);lon=np.concatenate([z['node_lon'] for z in Z]);uid,first,inv=np.unique(ids,return_index=True,return_inverse=True);node_lat=lat[first];node_lon=lon[first];del ids,lat,lon
observed=np.concatenate([z['observed_way_id'] for z in Z]);versions=np.concatenate([z['observed_way_version'] for z in Z]);allways,wayinv=np.unique(observed,return_inverse=True);latest=np.zeros(len(allways),np.uint32);np.maximum.at(latest,wayinv,versions);del observed,versions,wayinv
off=np.cumsum([0]+[len(z['node_osm_id']) for z in Z]);U=np.concatenate([inv[off[k]+z['u']] for k,z in enumerate(Z)]);V=np.concatenate([inv[off[k]+z['v']] for k,z in enumerate(Z)]);del inv
fields=['way_id','way_version','segment_index','speed_forward_kmh','speed_backward_kmh','oneway','limited_access'];A={n:np.concatenate([z[n] for z in Z]) for n in fields};original_segments=len(U);eligible=A['way_version']==latest[np.searchsorted(allways,A['way_id'])];discarded_old=int((~eligible).sum());U,V=U[eligible],V[eligible];A={n:a[eligible] for n,a in A.items()};del eligible
sort=np.lexsort((A['segment_index'],A['way_id']));starts=np.r_[True,(A['way_id'][sort[1:]]!=A['way_id'][sort[:-1]])|(A['segment_index'][sort[1:]]!=A['segment_index'][sort[:-1]])];duplicates=np.flatnonzero(~starts)
for n,a in {'u':U,'v':V,**A}.items():
 if len(duplicates) and not np.array_equal(a[sort[duplicates]],a[sort[duplicates-1]]):raise ValueError('Same way/version/segment conflict: '+n)
keep=sort[starts];removed_duplicates=len(U)-len(keep);U,V=U[keep],V[keep];A={n:a[keep] for n,a in A.items()};del sort,starts,keep
used,remap=np.unique(np.r_[U,V],return_inverse=True);N=len(U);U,V=remap[:N].astype(np.int32),remap[N:].astype(np.int32);node_lat,node_lon,uid=node_lat[used],node_lon[used],uid[used];assert len(uid)<2**31
la1,lo1,la2,lo2=np.radians(node_lat[U]),np.radians(node_lon[U]),np.radians(node_lat[V]),np.radians(node_lon[V]);length=2*6371000*np.arcsin(np.sqrt(np.clip(np.sin((la2-la1)/2)**2+np.cos(la1)*np.cos(la2)*np.sin((lo2-lo1)/2)**2,0,1)))
out.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(str(out)+'.partial.npz',format_version=np.array([2],np.uint8),u=U,v=V,length_m=length.astype(np.float32),node_lat=node_lat,node_lon=node_lon,node_osm_id=uid,observed_way_id=allways,observed_way_version=latest,**A);Path(str(out)+'.partial.npz').rename(out)
with out.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
m={'state':'built_static_model_unvalidated','jst':datetime.now(timezone(timedelta(hours=9))).isoformat(),'graph_sha256':digest,'format_version':2,'nodes':len(uid),'segments':len(U),'input_segments':original_segments,'discarded_older_way_segments':discarded_old,'removed_same_road_segment_duplicates':removed_duplicates,'sources':[{'path':str(p),'sha256':m['graph_sha256'],'replication_timestamp':m.get('replication_timestamp')} for p,m in zip(paths,metas)],'source_replication_timestamps':sorted({m.get('replication_timestamp','') for m in metas}),'length_rule':'Recomputed from selected newest-extract node coordinates; no averaging','version_rule':'Max observed way version, including observed ways excluded by road/access policy; same road/version/segment attribute conflicts fail','limitations':['Deleted ways absent from newer extracts cannot be identified from historical snapshots alone','No turn/barrier/conditional/endpoint enforcement; see component manifests'],'elapsed_seconds':time.monotonic()-started,'national_access_results':False};Path(str(out)+'.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(m),flush=True)
