import pathlib,json,subprocess,sys,os,time,psutil,shutil,hashlib,datetime
root=pathlib.Path.cwd();b=root/'research/codex'; out=b/'R322_A1_rederived';runtime=b/'R322_A1_runtime_v2';ev=root/'research/shared_results/collaborator_report_20261026/evidence';old_results=root/'research/handoff/R-020_parent_hash_results_44.jsonl'; rows=[json.loads(x) for x in old_results.read_text(encoding='utf-8-sig').splitlines()]; parents={int(r['pref'][4:]):root/pathlib.Path(r['path']).parent for r in rows if r['state']=='match'}
for n in (14,27,29):
 chk=json.loads((b/f'R322_parent_rebuild/pref{n:02d}_hash_check.json').read_text());assert chk['match'];parents[n]=b/f'R322_parent_rebuild/pref{n:02d}'
assert len(parents)==47
now=lambda:datetime.datetime.now().astimezone().isoformat();p=out/'batch_job.json';assert not p.exists();state={'state':'running','started':now(),'completed':['03'],'scope':'A1 derived matrices, no sensitivity analyses','pref03':'pref03_attempt2'}
def save():p.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONIOENCODING='utf-8');save()
try:
 for n in range(1,48):
  pc=f'{n:02d}'
  if n==3:continue
  dest=out/f'pref{pc}'; assert not dest.exists()
  if psutil.virtual_memory().available<4*2**30 or shutil.disk_usage(out).free<8*2**30:raise RuntimeError('insufficient start resources')
  cmd=[sys.executable,str(runtime/'R054_derive_worker.py'),pc,str(parents[n]),str(dest)]
  with (out/f'pref{pc}.log').open('x',encoding='utf-8') as log:
   child=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));state.update(current_pref=pc,pid=child.pid,checked=now());save()
   while child.poll() is None:
    time.sleep(5);state.update(checked=now(),available_ram=psutil.virtual_memory().available,free_disk=shutil.disk_usage(out).free);save()
    if state['available_ram']<2*2**30 or state['free_disk']<4*2**30:
     try:
      proc=psutil.Process(child.pid)
      for c in proc.children(recursive=True):c.terminate()
      proc.terminate()
     except psutil.Error:pass
     child.wait();raise RuntimeError('resource guard')
   if child.returncode:raise RuntimeError(f'pref{pc} exit {child.returncode}')
  prev=json.loads((ev/f'pref{pc}_derived_matrix_job.json').read_text(encoding='utf-8-sig'));proof=dest/'readback_validation.json'
  with proof.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
  if actual!=prev['readback_validation_sha256']:raise RuntimeError(f'pref{pc} readback hash mismatch expected {prev["readback_validation_sha256"]} actual {actual}')
  state['completed'].append(pc);save();print(f'pref{pc} readback match; {len(state["completed"])}/47',flush=True)
 state.update(state='completed_all47_readback_hashes_match',finished=now());save();print('all47 complete',flush=True)
except BaseException as e:
 state.update(state='failed_halt',error=repr(e),finished=now());save();raise
