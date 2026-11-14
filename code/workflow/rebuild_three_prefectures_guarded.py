import pathlib,os,sys,json,subprocess,time,psutil,shutil,datetime,hashlib
b=pathlib.Path.cwd()/'research/codex'; root=b/'R322_parent_rebuild';root.mkdir(exist_ok=False); graph=b/'R322_graph_recovery/national_reviewed.npz'; proof=json.loads((graph.parent/'job.json').read_text(encoding='utf-8')); assert proof['state']=='completed_match'
producer=b/'R023_runtime/traveltime_national_graph.py'; helper=b/'R023_runtime/graph_integrity.py'; rt=b/'R032_memory_runtime'; population=b/'R021_inputs/mesh500.parquet'; master=b/'R023_runtime/master_frozen.csv'; ev=pathlib.Path.cwd()/'research/shared_results/collaborator_report_20261026/evidence'
expected={producer:'6693071466232ea121d677645355d4cc103d5c72d60c001deb88c87c44c2482e',helper:'e54d17cf3b3c0792cf9df26f1394e2f422a11888e160c49187499e3107bbebc9',population:'796bb7c90cca9c49d9d17ad0ae6a771322fb221fb2331b5a4410ecb466d12dd6',master:'ac69024aa01b762c451253f68da375790398186535d54e95a14351f7a8acf828'}
for p,h in expected.items():
 with p.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==h,str(p)
now=lambda:datetime.datetime.now().astimezone().isoformat();state={'state':'starting','started':now(),'completed':[],'graph_sha256':proof['actual_sha256'],'scope':'parent matrices only; no sensitivity analysis'};job=root/'job.json'
def save():job.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
env=os.environ.copy();env.update(PVN_GRAPH=str(graph),PVN_SPEED_FACTOR='.9',PVN_SNAP_MAX_M='1000',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',PYTHONIOENCODING='utf-8');env.pop('PVN_ANALYSIS_TAG',None);save()
try:
 for pc in ['14','27','29']:
  if psutil.virtual_memory().available<4*2**30 or shutil.disk_usage(root).free<8*2**30: raise RuntimeError('insufficient resources before start')
  dest=root/f'pref{pc}'; receipt=root/f'pref{pc}_adapter.json'; profile=root/f'pref{pc}_profile.json';old=json.loads((ev/f'pref{pc}_parent_matrix_job.json').read_text(encoding='utf-8-sig'))
  cmd=[sys.executable,str(rt/'profile_R032_python.py'),str(rt/'run_R032_memory_adapter.py'),str(profile),f'pref{pc}','none',str(population),str(master),str(dest),str(receipt)]
  with (root/f'pref{pc}.log').open('x',encoding='utf-8') as log:
   child=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));state.update(state='running',current_pref=pc,pid=child.pid);save();low=0
   while child.poll() is None:
    time.sleep(5);ram=psutil.virtual_memory().available;disk=shutil.disk_usage(root).free;state.update(available_ram=ram,free_disk=disk,checked=now());save();low=low+1 if ram<2*2**30 or disk<4*2**30 else 0
    if low>=2:child.terminate();child.wait();raise RuntimeError('resource guard stopped process')
   if child.returncode:raise RuntimeError(f'{pc} process exit {child.returncode}')
  actual=json.loads((dest/'job.json').read_text(encoding='utf-8')); fields=['origins_total','completed_origins','pairs_total']; comparisons={k:{'recorded':old.get(k),'actual':actual.get(k),'match':old.get(k)==actual.get(k)} for k in fields}
  state['comparisons_'+pc]=comparisons;save()
  if actual.get('state')!='completed_static_graph_scenario' or not all(x['match'] for x in comparisons.values()):raise RuntimeError('record mismatch for '+pc)
  state['completed'].append(pc);save();print(f'pref{pc} counts match',flush=True)
 state['state']='completed_counts_match';state['finished']=now();save();print(json.dumps(state,ensure_ascii=False),flush=True)
except BaseException as e:
 state.update(state='failed_halt',error=repr(e),finished=now());save();raise
