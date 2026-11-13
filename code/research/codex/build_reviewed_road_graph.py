"""Build a separately versioned static graph, retaining OSM way identity/version.
Turn restrictions/conditional access/endpoint-only access remain explicit limitations.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,array,time,json,hashlib,collections,sys
import numpy as np,osmium
sys.path.insert(0,str(Path(__file__).resolve().parent))
from graph_integrity import SPEED,permitted,direction,directional_speeds,access_value
ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('out');ap.add_argument('--node-index');args=ap.parse_args();src=Path(args.source);out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
if out.exists() or Path(str(out)+'.partial.npz').exists():raise FileExistsError('Preserve previous graph/output; choose separate run directory')
started=time.monotonic();counts=collections.Counter()
with src.open('rb') as f:source_hash=hashlib.file_digest(f,'sha256').hexdigest()
reader=osmium.io.Reader(str(src));header=reader.header();replication=header.get('osmosis_replication_timestamp');reader.close()
class H(osmium.SimpleHandler):
 def __init__(self):
  super().__init__();self.nid=array.array('q');self.lat=array.array('d');self.lon=array.array('d');self.start=array.array('q');self.wid=array.array('q');self.ver=array.array('I');self.fspeed=array.array('f');self.bspeed=array.array('f');self.ow=array.array('b');self.limited=array.array('b');self.allwid=array.array('q');self.allver=array.array('I')
 def way(self,w):
  self.allwid.append(int(w.id));self.allver.append(int(w.version));hw=w.tags.get('highway')
  if hw not in SPEED:return
  counts['selected_highway_ways']+=1;t={str(k):str(v) for k,v in w.tags}
  if not permitted(t):counts['access_excluded']+=1;return
  if hw=='service' and t.get('service') in ('parking_aisle','driveway'):counts['service_policy_excluded']+=1;return
  ow=direction(t)
  if ow is None:counts['unsupported_oneway_excluded']+=1;return
  fs,bs=directional_speeds(t)
  if fs<=0 or bs<=0:counts['zero_speed_excluded']+=1;return
  if any(k.endswith(':conditional') for k in t):counts['conditional_tag_present_not_time_evaluated']+=1
  if access_value(t)[0] in ('destination','customers','delivery'):counts['endpoint_only_access_not_restricted_to_endpoints']+=1
  try:pts=[(n.ref,n.lat,n.lon) for n in w.nodes]
  except osmium.InvalidLocationError:counts['missing_location_ways']+=1;return
  if len(pts)<2:return
  self.start.append(len(self.nid));self.wid.append(int(w.id));self.ver.append(int(w.version));self.fspeed.append(fs);self.bspeed.append(bs);self.ow.append(ow);self.limited.append(hw.startswith('motorway') or t.get('motorroad')=='yes')
  for ni,la,lo in pts:self.nid.append(ni);self.lat.append(la);self.lon.append(lo)
  counts['included_ways']+=1
 def relation(self,r):
  if r.tags.get('type')=='restriction':counts['restriction_relations_not_applied']+=1
 def node(self,n):
  if n.tags.get('barrier') is not None:counts['barrier_nodes_not_applied']+=1
index_path=Path(args.node_index) if args.node_index else Path(str(out)+'.nodeidx');index_path.parent.mkdir(parents=True,exist_ok=True)
if index_path.exists():raise FileExistsError('Preserve existing node index')
h=H();h.apply_file(str(src),locations=True,idx='sparse_file_array,'+str(index_path));print(json.dumps({'stage':'read','counts':dict(counts),'elapsed':time.monotonic()-started}),flush=True)
if not len(h.start):raise ValueError('No supported road ways; do not publish an empty graph')
nid=np.frombuffer(h.nid,np.int64);lat=np.frombuffer(h.lat,np.float64);lon=np.frombuffer(h.lon,np.float64);starts=np.frombuffer(h.start,np.int64);ends=np.r_[starts[1:],len(nid)];seg_way=np.repeat(np.arange(len(starts)),ends-starts-1);mask=np.ones(len(nid),bool);mask[ends-1]=False;ia=np.nonzero(mask)[0];ib=ia+1
la1,lo1,la2,lo2=np.radians(lat[ia]),np.radians(lon[ia]),np.radians(lat[ib]),np.radians(lon[ib]);length=2*6371000*np.arcsin(np.sqrt(np.clip(np.sin((la2-la1)/2)**2+np.cos(la1)*np.cos(la2)*np.sin((lo2-lo1)/2)**2,0,1)))
ids,first,inv=np.unique(nid,return_index=True,return_inverse=True);assert len(ids)<2**31;segment_index=ia-starts[seg_way]
np.savez_compressed(str(out)+'.partial.npz',format_version=np.array([2],np.uint8),u=inv[ia].astype(np.int32),v=inv[ib].astype(np.int32),length_m=length.astype(np.float32),speed_forward_kmh=np.frombuffer(h.fspeed,np.float32)[seg_way],speed_backward_kmh=np.frombuffer(h.bspeed,np.float32)[seg_way],oneway=np.frombuffer(h.ow,np.int8)[seg_way],limited_access=np.frombuffer(h.limited,np.int8)[seg_way],way_id=np.frombuffer(h.wid,np.int64)[seg_way],way_version=np.frombuffer(h.ver,np.uint32)[seg_way],segment_index=segment_index.astype(np.int32),node_lat=lat[first],node_lon=lon[first],node_osm_id=ids,observed_way_id=np.frombuffer(h.allwid,np.int64),observed_way_version=np.frombuffer(h.allver,np.uint32))
Path(str(out)+'.partial.npz').rename(out)
with out.open('rb') as f:output_hash=hashlib.file_digest(f,'sha256').hexdigest()
meta={'state':'built_static_model_unvalidated','jst':datetime.now(timezone(timedelta(hours=9))).isoformat(),'source':str(src),'source_sha256':source_hash,'replication_timestamp':replication,'format_version':2,'graph_sha256':output_hash,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'helper_sha256':hashlib.sha256(Path(__file__).with_name('graph_integrity.py').read_bytes()).hexdigest(),'nodes':len(ids),'segments':len(ia),'counts':dict(counts),'elapsed_seconds':time.monotonic()-started,'limitations':['No turn-restriction state graph','No barrier or conditional-time enforcement','Endpoint-only restrictions not endpoint-specific','Parking aisles/driveways excluded by explicit policy','Static road-length cost, not live traffic or clinical availability'],'national_results':False};Path(str(out)+'.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(meta),flush=True)
