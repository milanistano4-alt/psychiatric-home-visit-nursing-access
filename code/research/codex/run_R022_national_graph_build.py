from pathlib import Path
from datetime import datetime,timezone,timedelta
import subprocess,sys,time,json,hashlib,shutil,os
import psutil
b=Path('research/codex');out=b/'R022_graphs';out.mkdir(exist_ok=False);job=b/'R022_build_job.json';assert not job.exists();scratch=Path('scratch/R022_indices');scratch.mkdir(exist_ok=True)
source=json.loads((b/'R021_graph_review/national_road_tag_audit.json').read_text());assert source['state']=='completed' and len(source['sources'])==8
regions=sorted(source['sources'],key=lambda r:(not r['path'].startswith('hokkaido'),r['bytes']));now=lambda:datetime.now(timezone(timedelta(hours=9))).isoformat();state={'state':'running','started_jst':now(),'wrapper_pid':os.getpid(),'source_audit_sha256':hashlib.sha256((b/'R021_graph_review/national_road_tag_audit.json').read_bytes()).hexdigest(),'completed_regions':[],'phases':{},'clinical_or_access_results_validated':False,'source_date_uniform':False,'source_date_note':'Kansai Oct12; others Oct15. Public checksum lookup defaultDNSfailed then approval-review timeout. No new download claimed.'}
def write():job.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
write()
def run(name,cmd):
 log=out/(name+'.log');started=time.monotonic();low=0
 with log.open('w',encoding='utf-8') as f:
  p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));phase={'pid':p.pid,'command':cmd,'log':str(log),'state':'running'};state['phases'][name]=phase;state['current_phase']=name;write()
  while p.poll() is None:
   time.sleep(5);ram=psutil.virtual_memory().available;disk=shutil.disk_usage(out.resolve().anchor).free
   try:root=psutil.Process(p.pid);rss=sum(q.memory_info().rss for q in [root]+root.children(recursive=True) if q.is_running())
   except psutil.Error:rss=0
   phase.update(last_checked_jst=now(),elapsed_seconds=time.monotonic()-started,sampled_rss_max_bytes=max(phase.get('sampled_rss_max_bytes',0),rss),available_ram_bytes=ram,disk_free_bytes=disk);write();low=low+1 if ram<768*1024**2 or disk<2*1024**3 else 0
   if low>=2:p.terminate();phase['resource_guard_terminated']=True;p.wait();break
  phase.update(state='completed' if p.returncode==0 else 'failed',exit_code=p.returncode,elapsed_seconds=time.monotonic()-started,finished_jst=now());write()
  if p.returncode!=0:raise RuntimeError(name+' exited '+str(p.returncode)+'; preserve partial outputs and inspect before any restart')
try:
 for r in regions:
  region=Path(r['path']).name.split('-')[0];path=Path(r['path'])
  with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==r['sha256']
  target=out/(region+'.npz');run(region,[sys.executable,str(b/'build_reviewed_road_graph.py'),str(path),str(target),'--node-index',str(scratch/(region+'.nodeidx'))]);meta=json.loads(Path(str(target)+'.json').read_text());assert meta['source_sha256']==r['sha256'] and meta['counts'].get('missing_location_ways',0)==0;state['completed_regions'].append(region);write();print(json.dumps({'completed_regions':state['completed_regions'],'total':8}),flush=True)
 run('national_merge',[sys.executable,str(b/'merge_reviewed_road_graphs.py'),str(out/'national_reviewed.npz'),*[str(out/(Path(r['path']).name.split('-')[0]+'.npz')) for r in regions]])
 state.update(state='completed_static_graph_not_access_validated',finished_jst=now());write();print(json.dumps(state),flush=True)
except Exception as exc:
 state.update(state='failed_preserved_outputs',error=type(exc).__name__+': '+str(exc),finished_jst=now());write();raise
