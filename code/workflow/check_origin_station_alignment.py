import pathlib,json,hashlib,pandas as pd
R=pathlib.Path.cwd()/'research'; b=R/'codex/R322_A1_rederived'; summaries=R/'shared_results/R190_A1_all47_local_results'; old=json.loads((R/'shared_results/collaborator_report_20261026/evidence/original_national_FCA_summary.json').read_text(encoding='utf-8-sig')); done=[]
for p in range(1,48):
 pc=f'{p:02d}';d=b/('pref03_attempt2' if p==3 else f'pref{pc}');readback=d/'readback_validation.json'
 if not readback.exists():continue
 prior=summaries/f'pref{pc}/origins_results.csv'; keys=[v for k,v in old['input_hashes'].items() if f'pref{pc}\\analysis_reviewed_A1_R061\\origins_results.csv' in k];assert len(keys)==1
 with prior.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 o=pd.read_csv(d/'origins.csv',dtype={'omesh':str});s=pd.read_csv(d/'sites.csv',dtype={'omesh':str}); prev=pd.read_csv(prior,dtype={'omesh':str});assert o.omesh.tolist()==prev.omesh.tolist()
 st=s[(s.kind=='station') & s.official_in_pilot.astype(bool)].groupby('o').size().reindex(range(len(o)),fill_value=0)
 eq=st.to_numpy().tolist()==prev.st_in.astype(int).tolist();row={'pref':pc,'old_origin_file_hash_match':h==keys[0],'origin_mesh_order_match':True,'owned_station_counts_match':bool(eq),'owned_stations':int(st.sum())};done.append(row)
 if not row['old_origin_file_hash_match'] or not eq:raise ValueError(str(row))
p=R/'handoff/R-022_origin_station_alignment_progress.json';p.write_text(json.dumps(done,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'completed':len(done),'matched':sum(x['owned_station_counts_match'] for x in done),'prefectures':[x['pref'] for x in done]}))
