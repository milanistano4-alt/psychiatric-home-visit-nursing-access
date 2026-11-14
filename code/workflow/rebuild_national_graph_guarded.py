import pathlib,json,subprocess,sys,time,psutil,hashlib,os,shutil,datetime
b=pathlib.Path.cwd()/'research/codex'; src=b/'R022_graphs'; out=b/'R322_graph_recovery';out.mkdir(exist_ok=False)
meta=json.loads((src/'national_reviewed.npz.json').read_text(encoding='utf-8')); inputs=[pathlib.Path(x['path']) for x in meta['sources']]
for p,x in zip(inputs,meta['sources']):
 with p.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
 if h!=x['sha256']:raise ValueError(f'input hash mismatch {p}')
state={'state':'starting','expected_sha256':meta['graph_sha256'],'inputs_verified':len(inputs),'started':datetime.datetime.now().astimezone().isoformat()}; job=out/'job.json'
def save(): job.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
save();target=out/'national_reviewed.npz'; cmd=[sys.executable,str(b/'merge_reviewed_road_graphs.py'),str(target),*[str(p) for p in inputs]]
with (out/'merge.log').open('x',encoding='utf-8') as log:
 child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)); state.update(state='running',pid=child.pid);save(); low=0
 while child.poll() is None:
  time.sleep(5); mem=psutil.virtual_memory().available;disk=shutil.disk_usage(out).free
  try:
   proc=psutil.Process(child.pid);rss=sum(q.memory_info().rss for q in [proc]+proc.children(recursive=True) if q.is_running())
  except psutil.Error: rss=0
  state.update(available_ram=mem,free_disk=disk,peak_rss=max(state.get('peak_rss',0),rss),checked=datetime.datetime.now().astimezone().isoformat());save()
  low=low+1 if mem<2*2**30 or disk<4*2**30 else 0
  if low>=2:child.terminate();child.wait();state['guard_stop']=True;break
state['exit_code']=child.returncode
if child.returncode==0:
 with target.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
 state.update(actual_sha256=actual,state='completed_match' if actual==meta['graph_sha256'] else 'completed_hash_mismatch_halt')
else:state['state']='failed_halt'
state['finished']=datetime.datetime.now().astimezone().isoformat();save();print(json.dumps(state,ensure_ascii=False),flush=True)
