"""Compute only additional A1 origins plus two old controls per prefecture."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import sys,os,json,gc,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np,pandas as pd,pyarrow.dataset as ds,psutil
from R037_mapped_numeric import MappedNumericNPZ,digest
from artifact_hash import artifact_digest
import R052_delta_primitives as p
B=Path('research/codex');pc=sys.argv[1];OUT=B/'R052_delta_origins'/('pref'+pc);assert not OUT.exists();OUT.mkdir(parents=True)
DISK=Path('D:/PHVN-RES-20261024-R052-A1-delta');assert DISK.is_dir()
now=lambda:datetime.now(timezone(timedelta(hours=9))).isoformat()
job={'state':'preparing_delta','started_jst':now(),'pref_code':pc,'scope_prefectures':47,'source_frame_finalized':False,'output_type':'additional_A1_origin_rows_not_a_complete_matrix','SCC_filter_adopted':False}
def save():job['checked_jst']=now();(OUT/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
def guard():
    if psutil.virtual_memory().available<3*1024**3:raise MemoryError('Own delta worker guard')
save()
try:
    req=B/'R051_A1_origin_requirements/additional_origin_requirements.csv';frame=B/'R049_address_point_scenario_A1/registered_frame_A1_address_scenario.csv';popfile=B/'R021_inputs/mesh500.parquet';cmfile=B/'R040_A0_reuse_audit_v2/population_only_candidates47.csv';cache=B/'R037_cache_manifest.json';meta=json.loads(cache.read_text(encoding='utf-8'))
    assert digest(frame)=='571a7989820bf1840dac483662bbcd1718b748fbc2722e1db9f2fdccd9415f34' and digest(popfile)=='796bb7c90cca9c49d9d17ad0ae6a771322fb221fb2331b5a4410ecb466d12dd6'
    assert digest(meta['source_npz'])==meta['source_npz_sha256']=='5408d489e30834807b64a8e6fe2308bd39b6eeacd8e4bd7a6c86deb843028c44'
    extra=pd.read_csv(req,dtype={'pref_code':str,'omesh':str});extra=extra[extra.pref_code.eq(pc)];assert len(extra)>0
    cm=pd.read_csv(cmfile,dtype={'pref_code':str,'omesh':str});controls=cm[cm.pref_code.eq(pc)].omesh.head(2).tolist();assert len(controls)==len(set(controls))==2 and not(set(controls)&set(extra.omesh))
    origins=pd.DataFrame([{'omesh':m,'role':'delta'} for m in sorted(extra.omesh)]+[{'omesh':m,'role':'control'} for m in controls]);origins[['lat','lon']]=[p.center(m) for m in origins.omesh];origins['local_o']=np.arange(len(origins),dtype=np.int32)
    pop=pd.read_parquet(popfile,columns=['MESH_ID','pref_code','lat','lon']);pop['MESH_ID']=pop.MESH_ID.astype(str);G,bounds=p.geometry(pop,pc);del pop;gc.collect();guard()
    job.update(state='building_same_policy_graph',input_sha256={str(f):digest(f) for f in [req,frame,popfile,cmfile,cache,Path(meta['source_npz'])]},runtime_sha256={str(f):digest(f) for f in Path(__file__).parent.glob('*.py')},delta_origins=len(extra),control_origins=2,region_population_bounds=list(map(float,bounds)),graph_clip_margin_degrees=.65,source_graph_sha256=meta['source_npz_sha256']);save()
    z=MappedNumericNPZ(cache,np.load,verify=True);graph,tree,allowed,counts=p.clipped_graph(z,bounds,DISK/('pref'+pc+'_prefix.npy'));z.close();del z;gc.collect();guard()
    target,dg=p.snap(tree,allowed,G.lat.to_numpy(),G.lon.to_numpy());source,do=p.snap(tree,allowed,origins.lat.to_numpy(),origins.lon.to_numpy());del tree,allowed;gc.collect()
    G['snap_m']=dg;G['snap_valid']=dg<=1000;G['snap_status']=np.where(G.snap_valid,'within_distance_guard_unverified_barriers','unknown_over_snap_guard');origins['snap_m']=do;origins['snap_valid']=do<=1000;origins['snap_status']=np.where(origins.snap_valid,'within_distance_guard_unverified_barriers','unknown_over_snap_guard')
    G.to_parquet(OUT/'mesh_geom.parquet');origins.to_csv(OUT/'origins.csv',index=False,encoding='utf-8-sig');job.update(state='computing_delta_and_controls',graph=counts);save()
    parts=[]
    for start in range(0,len(origins),4):
        guard();stop=min(start+4,len(origins));f=p.edges(graph,source[start:stop],do[start:stop],target,dg,origins.snap_valid.to_numpy()[start:stop],G.snap_valid.to_numpy());f['o']+=np.int32(start);parts.append(f)
    pairs=pd.concat(parts,ignore_index=True);delta=pairs[pairs.o<len(extra)].reset_index(drop=True);control=pairs[pairs.o>=len(extra)].reset_index(drop=True);delta.to_parquet(OUT/'delta.parquet',index=False);control.to_parquet(OUT/'controls.parquet',index=False);del graph,parts,pairs;gc.collect();guard()
    main=json.loads((B/'R032_national_job.json').read_text(encoding='utf-8'));parent=Path(main['directory_by_prefecture'][pc]) if pc in main['directory_by_prefecture'] else B/'R032_prefectures'/('pref'+pc);comparison={'state':'pending_original_parent_not_complete'}
    if (parent/'job.json').exists() and json.loads((parent/'job.json').read_text(encoding='utf-8')).get('state')=='completed_static_graph_scenario':
        before=artifact_digest(parent/'tt_origin.parquet');pg=pd.read_parquet(parent/'mesh_geom.parquet');assert list(pg.columns)==list(G.columns) and len(pg)==len(G)
        for col in G:assert np.array_equal(pg[col].to_numpy(),G[col].to_numpy()),('geometry mismatch',pc,col)
        po=pd.read_csv(parent/'origins.csv',dtype={'omesh':str});mapping=dict(zip(po.omesh,po.index));indices=[int(mapping[m]) for m in controls];old=ds.dataset(parent/'tt_origin.parquet',format='parquet').to_table(filter=ds.field('o').isin(indices)).to_pandas();verified=[]
        for row in origins[origins.role.eq('control')].itertuples():
            original=old[old.o.eq(mapping[row.omesh])].sort_values('g');current=control[control.o.eq(row.local_o)].sort_values('g');assert len(original)==len(current)>0
            for col in ['g','band','t_exact']:assert np.array_equal(original[col].to_numpy(),current[col].to_numpy()),('control mismatch',pc,row.omesh,col)
            assert bool(po.loc[mapping[row.omesh],'snap_valid'])==row.snap_valid
            verified.append({'omesh':row.omesh,'parent_o':int(mapping[row.omesh]),'local_o':int(row.local_o),'pairs_bit_identical':len(current)})
        assert artifact_digest(parent/'tt_origin.parquet')==before
        comparison={'state':'geometry_and_both_control_sparse_rows_exactly_reproduced','parent':str(parent),'parent_time_sha256':before,'controls':verified,'geometry_same_bytes':digest(parent/'mesh_geom.parquet')==digest(OUT/'mesh_geom.parquet'),'parent_artifacts_sha256':{n:artifact_digest(parent/n) for n in ['job.json','origins.csv','mesh_geom.parquet']}}
    for f,h in job['input_sha256'].items():assert digest(f)==h
    job.update(state='completed_additional_origin_delta_not_full_A1_matrix',finished_jst=now(),delta_pairs=len(delta),control_pairs=len(control),control_comparison=comparison,geometry_sha256=digest(OUT/'mesh_geom.parquet'),origins_sha256=digest(OUT/'origins.csv'),delta_sha256=digest(OUT/'delta.parquet'),controls_sha256=digest(OUT/'controls.parquet'),route_horizon_minutes=60,speed_factor=.9,top_speed_kmh=40,connection_speed_kmh=15,snap_max_m=1000,A1_full_matrix_completed=False);save();print(json.dumps({'pref_code':pc,'delta_origins':len(extra),'delta_pairs':len(delta),'control_state':comparison['state']}),flush=True)
except BaseException as exc:job.update(state='failed_outputs_preserved',error=repr(exc));save();raise
