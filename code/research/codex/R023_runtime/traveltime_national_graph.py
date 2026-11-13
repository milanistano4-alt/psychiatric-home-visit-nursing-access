"""Static-road scenario matrix with explicit source ownership and snap uncertainty.
Usage: python traveltime_reviewed_graph.py prefNN none mesh500.parquet master.csv NEW_OUT
PVN_GRAPH points to reviewed format2. PVN_SPEED_FACTOR and PVN_SNAP_MAX_M define scenarios.
Only complete jobs may feed the reviewed analysis. This is not observed clinical access.
"""
import sys, os, json, time, re, hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pyarrow as pa
import pyarrow.parquet as pq
sys.path.insert(0,str(Path(__file__).resolve().parent))
from graph_integrity import directed_time_csr
import numpy as np, pandas as pd, shapely
from shapely.geometry import shape
from multiprocessing import Pool
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
import pilot_config as runtime_pilot_config
from pilot_config import PREF_NAMES, PILOTS, TMAX, STEP, TOP_SPEED, BUFFER_DEG, CAND_MIN_POP, REFINE_BANDS_BY_PILOT

REFINE_BANDS = {25, 30, 35}   # 軽量版：主要評価項目 τ=30 の付近だけ直接時間で判定（10/15/20分は帯で判定）
pilot, cfg, meshf, masterf, out = sys.argv[1:6]
P = PILOTS[pilot]
if P['shicode'] is not None:raise ValueError('Reviewed nationwide runner currently requires whole-prefecture ownership; no silent municipal geometry ownership')
if Path(out).exists():raise FileExistsError('Do not overwrite or restart an existing pilot; inspect the job first')
Path(out).mkdir(parents=True)
job={'state':'preparing','pilot':pilot,'started_jst':datetime.now(timezone(timedelta(hours=9))).isoformat(),'frames_are_finalized_cohort':False,'national_result':False}
jobpath=Path(out)/'job.json'
def digest_file(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record():jobpath.write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
record()
owner_names={PREF_NAMES[int(k)-1] for k in P['pref_codes']}
REFINE_BANDS = REFINE_BANDS_BY_PILOT.get(pilot, REFINE_BANDS)

comp = pd.read_parquet(meshf)[['MESH_ID', 'pref_code', 'SHICODE', 'PTN_2020', 'PTN_2025', 'lat', 'lon']].copy()
comp['MESH_ID'] = comp.MESH_ID.astype(str)
codes = comp.SHICODE.astype(str).str.split(r'[^0-9]+')
comp['multi_muni'] = codes.str.len() > 1
sel = comp.pref_code.isin(P['pref_codes'])
if P['shicode']: sel &= codes.apply(lambda cs: any(c in P['shicode'] for c in cs))
comp['in_pilot'] = sel
geom = comp.groupby('MESH_ID', as_index=False).agg(lat=('lat', 'mean'), lon=('lon', 'mean'))
D = comp[comp.in_pilot]
minx, maxx, miny, maxy = D.lon.min(), D.lon.max(), D.lat.min(), D.lat.max()
box = lambda df: df.lon.between(minx - BUFFER_DEG, maxx + BUFFER_DEG) & df.lat.between(miny - BUFFER_DEG, maxy + BUFFER_DEG)
G = geom[box(geom)].reset_index(drop=True)                    # 道路計算の対象（幾何）
G['in_pilot'] = G.MESH_ID.isin(D.MESH_ID)
gi = {m: k for k, m in enumerate(G.MESH_ID)}
C_ = comp[comp.MESH_ID.isin(gi)].copy(); C_['g'] = C_.MESH_ID.map(gi)  # 人口成分 → 幾何の番号
C_.to_parquet(f'{out}/pop_components.parquet'); G.to_parquet(f'{out}/mesh_geom.parquet')

L=pd.read_csv(masterf,dtype=str)
raw_lat=pd.to_numeric(L.lat,errors='coerce');raw_lon=pd.to_numeric(L.lon,errors='coerce');L['_geo_ok']=np.isfinite(raw_lat)&np.isfinite(raw_lon)&raw_lat.between(-90,90)&raw_lon.between(-180,180)
owned_frame=L[L['種別'].eq('ステーション')&L.pref.isin(owner_names)]
job['facility_frame_missing_coordinates_all']=int((L['種別'].eq('ステーション')&~L._geo_ok).sum());job['facility_frame_owned_total']=len(owned_frame);job['facility_frame_missing_coordinates']=int((~owned_frame._geo_ok).sum());record()
S=L[L['種別'].eq('ステーション')&L._geo_ok].copy()
S['lat'] = S.lat.astype(float); S['lon'] = S.lon.astype(float)
S = S[box(S)|S.pref.isin(owner_names)][['id', 'pref', 'lat', 'lon', '位置の出どころ']].rename(columns={'位置の出どころ': 'geo_src'})
# 60分×最高40km/h＝道路で40km。直線距離が40kmを超える事業所は地域内に60分で届かないので除く
from scipy.spatial import cKDTree
_lat0 = float(D.lat.mean())
def sphere_points(lat,lon):
    la=np.radians(np.asarray(lat,dtype=float));lo=np.radians(np.asarray(lon,dtype=float));return np.c_[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]
def arc_m(chord):return 2*6371000*np.arcsin(np.clip(np.asarray(chord,dtype=float)/2,0,1))
chord,_=cKDTree(sphere_points(D.lat.values,D.lon.values)).query(sphere_points(S.lat.values,S.lon.values))
dmin=arc_m(chord)/1000
S = S[(dmin <= TOP_SPEED * TMAX / 60.0 + 1.0)|S.pref.isin(owner_names)]  # conservative allowance for up to500m origin aggregation
S['kind'] = 'station'
# 候補：地域内の1kmメッシュごとに、最も人口の多い500mメッシュの中心（人口は成分の合計）
gp = D.groupby('MESH_ID').PTN_2020.sum().reset_index().merge(G[['MESH_ID', 'lat', 'lon']], on='MESH_ID')
gp['m3'] = gp.MESH_ID.str[:8]
top = gp.sort_values('PTN_2020', ascending=False).groupby('m3').head(1)
pop1k = gp.groupby('m3').PTN_2020.sum().rename('pop1k')
top = top.join(pop1k, on='m3'); top = top[top.pop1k >= CAND_MIN_POP]
Cd = pd.DataFrame({'id': 'cand_' + top.m3, 'pref': P['name'], 'lat': top.lat, 'lon': top.lon, 'geo_src': 'mesh', 'kind': 'candidate'})
sites = pd.concat([S, Cd], ignore_index=True)
def mesh500(lat, lon):
    p = np.floor(lat * 1.5).astype(int); u = np.floor(lon - 100).astype(int)
    q = np.floor((lat * 1.5 - p) * 8).astype(int); v = np.floor((lon - 100 - u) * 8).astype(int)
    r = np.floor(((lat * 1.5 - p) * 8 - q) * 10).astype(int); w = np.floor(((lon - 100 - u) * 8 - v) * 10).astype(int)
    a = np.floor((((lat * 1.5 - p) * 8 - q) * 10 - r) * 2).astype(int); b = np.floor((((lon - 100 - u) * 8 - v) * 10 - w) * 2).astype(int)
    return np.array([f'{P_:02d}{U:02d}{Q}{V}{R}{W}{1 + A_ * 2 + B}' for P_, U, Q, V, R, W, A_, B in zip(p, u, q, v, r, w, a, b)])
def mesh_center(code):
    c = str(code); h = int(c[8])
    lat = int(c[0:2]) / 1.5 + int(c[4]) * 5 / 60 + int(c[6]) * 30 / 3600 + (h in (3, 4)) * 15 / 3600 + 7.5 / 3600
    lon = int(c[2:4]) + 100 + int(c[5]) * 7.5 / 60 + int(c[7]) * 45 / 3600 + (h in (2, 4)) * 22.5 / 3600 + 11.25 / 3600
    return lat, lon
sites['omesh'] = mesh500(sites.lat.values, sites.lon.values)
O = sites.groupby('omesh').agg(has_station=('kind', lambda k: (k == 'station').any()), n_sites=('kind', 'size')).reset_index()
O[['lat', 'lon']] = [mesh_center(c) for c in O.omesh]
O['kind'] = np.where(O.has_station, 'station', 'candidate')
sites['o'] = sites.omesh.map({m: k for k, m in enumerate(O.omesh)})
from pilot_config import PREF_NAMES
owner_names={PREF_NAMES[int(k)-1] for k in P['pref_codes']}
sites['official_in_pilot']=sites['pref'].isin(owner_names) & sites.kind.eq('station')
sites['owner_pref_codes']=','.join(P['pref_codes'])
job['known_owned_sites_included']=int(sites.official_in_pilot.sum());assert job['known_owned_sites_included']==job['facility_frame_owned_total']-job['facility_frame_missing_coordinates'];record()
O.to_csv(f'{out}/origins.csv', index=False)
print('origins (500m meshes)', len(O), 'for sites', len(sites), flush=True)

# ===== ここから v0.4：道路グラフの最短時間（scipy Dijkstra）。等時間圏・行列APIは使わない =====
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
GRAPH = os.environ['PVN_GRAPH']                    # 20_build_graph.py の出力（.npz）
CONNECT_KMH = 15.0                                  # メッシュ中心・事業所→最寄りの道路節点までの接続（直線距離をこの速度で加算）
SNAP_WARN_M = 1000.0                                # これより遠い接続は「道路非接続の疑い」として旗
z = np.load(GRAPH)
assert int(z['format_version'][0])==2
u,v,Lm,fs,bs,ow,limited=z['u'],z['v'],z['length_m'],z['speed_forward_kmh'],z['speed_backward_kmh'],z['oneway'],z['limited_access']
nlat, nlon = z['node_lat'], z['node_lon']
# 地域の範囲（＋余白）に入る節点だけで部分グラフを作る（全国グラフでもメモリと時間を抑える）
_m = 0.65
inb = (nlon >= minx - _m) & (nlon <= maxx + _m) & (nlat >= miny - _m) & (nlat <= maxy + _m)
ke = inb[u] & inb[v]
newid = np.cumsum(inb) - 1
u,v,Lm,fs,bs,ow,limited=newid[u[ke]],newid[v[ke]],Lm[ke],fs[ke],bs[ke],ow[ke],limited[ke]
nlat, nlon = nlat[inb], nlon[inb]
SPEED_FACTOR = float(os.environ.get('PVN_SPEED_FACTOR', '0.9'))   # 21_ の較正（奈良、Valhallaに対し差の中央値−0.6分）
nN=len(nlat)
Gc=directed_time_csr({'u':u,'v':v,'oneway':ow,'length_m':Lm,'speed_forward_kmh':fs,'speed_backward_kmh':bs,'node_osm_id':np.arange(nN)},TOP_SPEED,SPEED_FACTOR)
# 吸着先：高速道路・自動車専用道路だけに接する節点は除く（出入口以外から乗れないため）
hw_only = np.zeros(nN, bool)
deg = np.bincount(np.concatenate([u, v]), minlength=nN)
fast = limited.astype(bool)
degf = np.bincount(np.concatenate([u[fast], v[fast]]), minlength=nN)
ok_node = (deg > 0) & (degf < deg)
lat0 = float(D.lat.mean())
def P(lat,lon):return sphere_points(lat,lon)
okidx = np.nonzero(ok_node)[0]
if not len(okidx):raise ValueError('No eligible road nodes in clipped graph')
tree = cKDTree(P(nlat[okidx], nlon[okidx]))
dO,iO=tree.query(P(O.lat.values,O.lon.values));dO=arc_m(dO);srcN=okidx[iO]
dG,iG=tree.query(P(G.lat.values,G.lon.values));dG=arc_m(dG);tgtN=okidx[iG]
SNAP_MAX=float(os.environ.get('PVN_SNAP_MAX_M','1000'))
if not 0<SNAP_MAX<=1000:raise ValueError('Conservative snap guard must be in(0,1000]meters')
G['snap_m']=dG;O['snap_m']=dO
G['snap_valid']=dG<=SNAP_MAX;O['snap_valid']=dO<=SNAP_MAX
G['snap_status']=np.where(G.snap_valid,'within_distance_guard_unverified_barriers','unknown_over_snap_guard');O['snap_status']=np.where(O.snap_valid,'within_distance_guard_unverified_barriers','unknown_over_snap_guard')
# A short connector still does not prove a lawful/no-water crossing. Preserve this limitation.
G.to_parquet(f'{out}/mesh_geom.parquet');sites.to_csv(f'{out}/sites.csv',index=False,encoding='utf-8-sig')
G[['MESH_ID', 'snap_m']].to_parquet(f'{out}/mesh_snap.parquet'); O.to_csv(f'{out}/origins.csv', index=False)
print('graph nodes', nN, 'edges', Gc.nnz, 'mesh snap>1km', int((dG > SNAP_WARN_M).sum()), 'origin snap>1km', int((dO > SNAP_WARN_M).sum()), flush=True)
LIMIT = TMAX * 60.0
INP = G.in_pilot.values
if __name__ == '__main__':
    t0=time.time();B=8;parts=[];pair_count=0;chunk_start=0
    chunks=Path(out)/'tt_origin.parquet';chunks.mkdir();job.update(state='running',matrix_storage_policy='parquet_directory_128_origins',matrix_save_policy='all_origins_all_targets_within_horizon',external_horizon_minutes=TMAX,connection_distance_metric='great_circle_sphere6371000',helper_sha256=digest_file(Path(__file__).with_name('graph_integrity.py')),pilot_config_sha256=digest_file(Path(runtime_pilot_config.__file__)),top_speed_kmh=TOP_SPEED,candidate_min_population=CAND_MIN_POP,runtime_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_role_sha256={'population':digest_file(meshf),'master':digest_file(masterf),'graph':digest_file(GRAPH)},origins_total=len(O),completed_origins=0,chunk_files=[],speed_factor=SPEED_FACTOR,snap_max_m=SNAP_MAX,source_sha256={str(p):digest_file(p) for p in [meshf,masterf,GRAPH]},graph_metadata=str(GRAPH)+'.json',limitations=['Static graph; no turn/barrier/conditional enforcement','Connectors distance guarded but no crossing validation','500m origins differ from actual facility locations','Facility master is not a verified uniform-date census']);record()
    # 目的地の節点ごとにメッシュをまとめる（同じ節点に吸着したメッシュは同じ道路時間）
    order = np.argsort(tgtN); tn_sorted = tgtN[order]
    for s in range(0, len(O), B):
        idx = np.arange(s, min(s + B, len(O)))
        dist = dijkstra(Gc, directed=True, indices=srcN[idx], limit=LIMIT)       # 秒
        T = dist[:, tgtN]                                                        # (B, |G|)
        T=T+(dO[idx,None]+dG[None,:])/(CONNECT_KMH/3.6)
        T[~O.snap_valid.values[idx],:]=np.inf;T[:,~G.snap_valid.values]=np.inf
        for r, k in enumerate(idx):
            m = np.isfinite(T[r]) & (T[r] <= LIMIT)
            keep=m  # retain all origins' external-demand edges, not only current stations
            gi = np.nonzero(keep)[0]
            tmin = (T[r, gi] / 60.0).astype(np.float32)
            parts.append(pd.DataFrame({'g': gi.astype(np.int32), 'o': np.int32(k),
                                       'band': (np.ceil(tmin / STEP) * STEP).clip(STEP, TMAX).astype(np.uint8), 't_exact': tmin}))
        job['processed_origins']=int(s+len(idx))
        if (s+len(idx))%128==0 or s+len(idx)==len(O):
            chunk=chunks/f'batch_{chunk_start:07d}.parquet';frame=pd.concat(parts,ignore_index=True);pair_count+=len(frame);frame.to_parquet(chunk,index=False);parts=[];chunk_start=int(s+len(idx));job['chunk_files'].append(str(chunk));job['completed_origins']=chunk_start
        job['last_checked_jst']=datetime.now(timezone(timedelta(hours=9))).isoformat();record()
        if (s // B) % 50 == 0: print(s + len(idx), '/', len(O), round(time.time() - t0), 's', flush=True)
    if not job['chunk_files']:raise ValueError('No complete durable origin chunks')
    sites['area30_km2'] = np.nan
    sites.to_csv(f'{out}/sites.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(columns=['id', 'err']).to_csv(f'{out}/fails.csv', index=False)
    assert job['completed_origins']==len(O)
    for p,h in job['source_sha256'].items():assert digest_file(p)==h
    job.update(state='completed_static_graph_scenario',finished_jst=datetime.now(timezone(timedelta(hours=9))).isoformat(),pairs_total=pair_count,input_hashes_unchanged=True,unknown_snap_origins=int((~O.snap_valid).sum()),unknown_snap_geometries=int((~G.snap_valid).sum()));record()
    print('pairs', pair_count, 'refined', pair_count, 'fails 0 sec', round(time.time() - t0), flush=True)
    print('todo 0 done', len(O))
