"""A1 derived matrix with independent full edge readback; no road recomputation."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import os,sys,json,csv,shutil
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq,pyarrow.dataset as ds,psutil
from artifact_hash import artifact_digest as sha
from R054_frame_layout import build
B=Path('research/codex');pc=sys.argv[1];parent=Path(sys.argv[2]);OUT=Path(sys.argv[3]);assert not OUT.exists();OUT.mkdir(parents=True)
now=lambda:datetime.now(timezone(timedelta(hours=9))).isoformat();job={'state':'preparing_A1_derivation','started_jst':now(),'pilot':'pref'+pc,'pref_code':pc,'scope_prefectures':47,'source_frame_finalized':False,'matrix_construction':'parent_origin_subset_plus_verified_delta','not_original_producer_execution':True}
def save():job['checked_jst']=now();(OUT/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
def guard():
    if psutil.virtual_memory().available<2*1024**3:raise MemoryError('Own derivation memory guard')
    if shutil.disk_usage(OUT).free<2*1024**3:raise OSError('Own derivation disk guard')
def records(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
save()
try:
    pj=json.loads((parent/'job.json').read_text(encoding='utf-8'));assert pj['state']=='completed_static_graph_scenario' and pj['pilot']=='pref'+pc and pj['completed_origins']==pj['origins_total']
    assert pj['runtime_script_sha256']=='6693071466232ea121d677645355d4cc103d5c72d60c001deb88c87c44c2482e' and pj['source_role_sha256']['master']=='ac69024aa01b762c451253f68da375790398186535d54e95a14351f7a8acf828'
    master=B/'R054_A1_inputs/master_A1_registered_station_view.csv';assert sha(master)=='c16889913f2204a7c9eafbafeb1b3ad468e6edca9c2034454749392f2c805b4d';frame_manifest=B/'R054_A1_inputs/manifest.json';fm=json.loads(frame_manifest.read_text(encoding='utf-8'));assert fm['master_view_sha256']==sha(master)
    population=B/'R021_inputs/mesh500.parquet';graph=B/'R322_graph_recovery/national_reviewed.npz';assert pj['source_role_sha256']['population']==sha(population)=='796bb7c90cca9c49d9d17ad0ae6a771322fb221fb2331b5a4410ecb466d12dd6';assert pj['source_role_sha256']['graph']==sha(graph)=='5408d489e30834807b64a8e6fe2308bd39b6eeacd8e4bd7a6c86deb843028c44'
    inputs={str(parent/n):sha(parent/n) for n in ['job.json','sites.csv','origins.csv','pop_components.parquet','mesh_geom.parquet','tt_origin.parquet']};inputs.update({str(p):sha(p) for p in [master,frame_manifest,population,graph,B/'R049_address_point_scenario_A1/registered_frame_A1_address_scenario.csv']})
    comp=pd.read_parquet(parent/'pop_components.parquet');geom=pd.read_parquet(parent/'mesh_geom.parquet');L=pd.read_csv(master,dtype=str);cand=pd.read_csv(B/'R040_A0_reuse_audit_v2/population_only_candidates47.csv',dtype={'pref_code':str,'omesh':str});sites,O,frame_counts=build(L,comp,geom,cand,pc)
    expected=pd.read_csv(B/'R051_A1_origin_requirements/origin_requirements47.csv',dtype={'pref_code':str}).set_index('pref_code').loc[pc];assert len(O)==int(expected.A1_policy_origins) and frame_counts['facility_frame_owned_total']==int(expected.registered_budget)
    po=records(parent/'origins.csv');old_mesh=[r['omesh'] for r in po];new_mesh=O.omesh.tolist();new_index={m:i for i,m in enumerate(new_mesh)};old_index={m:i for i,m in enumerate(old_mesh)};assert len(old_index)==len(po)
    missing=set(new_mesh)-set(old_mesh);lookup=np.array([new_index.get(m,-1) for m in old_mesh],np.int32);assert len(missing)==int(expected.additional_origins_needed)
    delta_manifest=B/'R052_delta_manifest.json';dm=json.loads(delta_manifest.read_text(encoding='utf-8'));assert dm['A1_frame_sha256']==fm['A1_source_sha256'];entry=next((e for e in dm['entries'] if e['pref_code']==pc),None);delta=None;delta_origins=[];delta_source={};control_proof={'state':'no_additional_rows_required'}
    if entry is not None:
        d=Path(entry['directory']);dj=json.loads((d/'job.json').read_text(encoding='utf-8'));assert sha(d/'job.json')==entry['job_sha256'] and dj['state']=='completed_additional_origin_delta_not_full_A1_matrix'
        for n,h in [('delta.parquet',entry['delta_sha256']),('controls.parquet',entry['controls_sha256']),('origins.csv',entry['origins_sha256']),('mesh_geom.parquet',entry['geometry_sha256'])]:assert sha(d/n)==h;delta_source[str(d/n)]=h
        delta_source[str(d/'job.json')]=entry['job_sha256'];dg=pd.read_parquet(d/'mesh_geom.parquet')
        for col in geom:assert np.array_equal(geom[col].to_numpy(),dg[col].to_numpy())
        do=records(d/'origins.csv');delta_origins=[r for r in do if r['role']=='delta'];assert {r['omesh'] for r in delta_origins}==missing;controls=[r for r in do if r['role']=='control'];assert len(controls)==2
        old_controls=ds.dataset([str(p) for p in sorted((parent/'tt_origin.parquet').glob('*.parquet'))],format='parquet').to_table(filter=ds.field('o').isin([old_index[r['omesh']] for r in controls])).to_pandas();saved_controls=pd.read_parquet(d/'controls.parquet');verified=0
        for r in controls:
            a=old_controls[old_controls.o.eq(old_index[r['omesh']])].sort_values('g');b=saved_controls[saved_controls.o.eq(int(r['local_o']))].sort_values('g');assert len(a)==len(b)>0
            for col in ['g','band','t_exact']:assert np.array_equal(a[col].to_numpy(),b[col].to_numpy())
            verified+=len(a)
        control_proof={'state':'both_controls_verified_against_completed_parent','pairs':verified};delta=pd.read_parquet(d/'delta.parquet')
    else:assert not missing
    meta={r['omesh']:r for r in po};meta.update({r['omesh']:r for r in delta_origins});assert set(new_mesh)<=set(meta)
    for col in ['lat','lon','snap_m','snap_status']:O[col]=[meta[m][col] for m in new_mesh]
    O['snap_valid']=[meta[m]['snap_valid']=='True' for m in new_mesh];assert all(r['snap_valid'] in ['True','False'] for r in meta.values())
    sites.to_csv(OUT/'sites.csv',index=False,encoding='utf-8-sig');O.to_csv(OUT/'origins.csv',index=False,encoding='utf-8-sig');shutil.copy2(parent/'pop_components.parquet',OUT/'pop_components.parquet');shutil.copy2(parent/'mesh_geom.parquet',OUT/'mesh_geom.parquet');target=OUT/'tt_origin.parquet';target.mkdir()
    job.update(state='deriving_and_reading_back_parent_edges',input_artifact_sha256=inputs,delta_input_artifact_sha256=delta_source,source_role_sha256={'master':sha(master),'population':sha(population),'graph':sha(graph)},source_sha256={str(p):sha(p) for p in [master,population,graph]},source_A1_frame_sha256=fm['A1_source_sha256'],**frame_counts);save()
    source_files=sorted((parent/'tt_origin.parquet').glob('*.parquet'));assert source_files;read_rows=kept_rows=0;last_source_key=-1
    for seq,src in enumerate(source_files):
        guard();dest=target/f'parent_{seq:05d}.parquet';writer=None
        try:
            for batch in pq.ParquetFile(src).iter_batches(batch_size=65536):
                t=pa.Table.from_batches([batch]);oi=t['o'].to_numpy();gg=t['g'].to_numpy();tt=t['t_exact'].to_numpy();assert (oi>=0).all() and (oi<len(lookup)).all() and (gg>=0).all() and (gg<len(geom)).all();assert np.isfinite(tt).all() and (tt>=0).all() and (tt<=60).all()
                keys=oi.astype(np.int64)*len(geom)+gg
                if len(keys):assert keys[0]>last_source_key and (np.diff(keys)>0).all();last_source_key=int(keys[-1])
                keep=lookup[oi]>=0;filtered=t.filter(pa.array(keep));mapped=lookup[oi[keep]];revised=filtered.set_column(filtered.schema.get_field_index('o'),filtered.schema.field('o'),pa.array(mapped,type=filtered.schema.field('o').type))
                if writer is None:writer=pq.ParquetWriter(dest,revised.schema,compression='zstd')
                writer.write_table(revised);read_rows+=len(t);kept_rows+=len(revised)
            if writer is None:
                empty=pq.read_table(src);assert len(empty)==0;writer=pq.ParquetWriter(dest,empty.schema,compression='zstd');writer.write_table(empty)
        finally:
            if writer is not None:writer.close()
        assert writer is not None
    assert read_rows==pj['pairs_total']
    added_rows=0
    if delta is not None:
        delta_map={int(r['local_o']):new_index[r['omesh']] for r in delta_origins};assert set(delta.o.unique())<=set(delta_map)
        revised_delta=delta.copy();revised_delta['o']=revised_delta.o.map(delta_map).astype(np.int32);revised_delta.to_parquet(target/'delta.parquet',index=False);added_rows=len(revised_delta)
    # Independent mapping from inverse membership and sorted old indices.
    old_kept=np.array(sorted(old_index[m] for m in new_mesh if m in old_index),np.int64);new_for_old=np.array([new_mesh.index(old_mesh[k]) for k in old_kept],np.int32);verified_rows=0
    for seq,src in enumerate(source_files):
        dest=target/f'parent_{seq:05d}.parquet';actual=pq.read_table(dest);offset=0
        for batch in pq.ParquetFile(src).iter_batches(batch_size=65536):
            t=pa.Table.from_batches([batch]);oi=t['o'].to_numpy();ix=np.searchsorted(old_kept,oi);keep=ix<len(old_kept);valid=np.flatnonzero(keep);keep[valid]=old_kept[ix[valid]]==oi[valid];expected_t=t.filter(pa.array(keep));actual_t=actual.slice(offset,len(expected_t));mapped=new_for_old[ix[keep]]
            for col in ['g','band','t_exact']:assert actual_t[col].equals(expected_t[col])
            assert np.array_equal(actual_t['o'].to_numpy(),mapped);offset+=len(expected_t);verified_rows+=len(expected_t)
        assert offset==len(actual)
    assert verified_rows==kept_rows
    if delta is not None:
        back=pd.read_parquet(target/'delta.parquet');reverse={new_index[r['omesh']]:int(r['local_o']) for r in delta_origins};old_o=back.o.map(reverse).astype(np.int32);assert np.array_equal(old_o,delta.o)
        for col in ['g','band','t_exact']:assert np.array_equal(back[col].to_numpy(),delta[col].to_numpy())
        assert not back.duplicated(['o','g']).any()
    for path,h in {**inputs,**delta_source}.items():assert sha(path)==h
    origin_counts=np.zeros(len(O),np.int64)
    for batch in ds.dataset([str(p) for p in sorted(target.glob('*.parquet'))],format='parquet').to_batches(columns=['o'],batch_size=65536,use_threads=False):origin_counts+=np.bincount(batch.column(0).to_numpy(),minlength=len(O))
    assert origin_counts.sum()==kept_rows+added_rows
    proof={'state':'completed_full_parent_subset_and_delta_independent_readback','parent_rows':read_rows,'parent_rows_retained':kept_rows,'parent_rows_removed':read_rows-kept_rows,'added_delta_rows':added_rows,'all_derived_rows_verified':kept_rows+added_rows,'new_origin_count':len(O),'old_origin_count':len(po),'new_origin_meshes':sorted(missing),'control_proof':control_proof,'source_parent_time_sha256':inputs[str(parent/'tt_origin.parquet')],'derived_time_sha256':sha(target),'derived_metadata_sha256':{n:sha(OUT/n) for n in ['sites.csv','origins.csv','pop_components.parquet','mesh_geom.parquet']}}
    (OUT/'readback_validation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');pd.DataFrame({'o':np.arange(len(O)),'omesh':new_mesh,'finite_pairs':origin_counts}).to_csv(OUT/'origin_pair_counts.csv',index=False,encoding='utf-8-sig')
    job.update(state='completed_A1_derived_parent_subset_and_delta',finished_jst=now(),parent_directory=str(parent),source_parent_job_sha256=inputs[str(parent/'job.json')],readback_validation_sha256=sha(OUT/'readback_validation.json'),runtime_sha256={str(p):sha(p) for p in Path(__file__).parent.glob('*.py')},origins_total=len(O),completed_origins=len(O),pairs_total=int(kept_rows+added_rows),external_horizon_minutes=60,matrix_save_policy='all_origins_all_targets_within_horizon',matrix_storage_policy='derived_parquet_directory',speed_factor=.9,top_speed_kmh=40,snap_max_m=1000,candidate_min_population=50,static_model_not_clinical_validation=True,complete_A1_national_dataset=False);save();print(json.dumps({'pref':pc,'parent_rows':read_rows,'retained':kept_rows,'delta_rows':added_rows,'derived_rows':kept_rows+added_rows,'independent_readback_complete':True}),flush=True)
except BaseException as e:job.update(state='failed_derivation_outputs_preserved',error=repr(e));save();raise



