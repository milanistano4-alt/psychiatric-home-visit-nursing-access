"""Resource-guarded queue for26 additional origins, never a duplicate full47 run."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import os,sys,json,csv,shutil,subprocess,time,hashlib
import psutil
B=Path('research/codex');R=B/'R052_runtime';O=B/'R052_delta_origins';STATE=B/'R052_delta_job.json';DISK=Path('D:/PHVN-RES-20261024-R052-A1-delta')
assert not R.exists() and not O.exists() and not STATE.exists() and not DISK.exists()
assert json.loads((B/'R052_primitive_tests_v2/summary.json').read_text(encoding='utf-8'))['checks']==56
assert DISK.parent.resolve()==Path('D:/').resolve()
R.mkdir();O.mkdir();DISK.mkdir()
for name in ['R052_delta_worker.py','R052_delta_primitives.py','R037_mapped_numeric.py']:shutil.copy2(B/name,R/name)
for name in ['graph_integrity.py','artifact_hash.py']:shutil.copy2(B/'R023_runtime'/name,R/name)
shutil.copy2(B/'R032_memory_runtime/profile_R032_python.py',R/'profile_self.py');shutil.copy2(Path(__file__),R/'controller_source_snapshot.py')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
now=lambda:datetime.now(timezone(timedelta(hours=9))).isoformat()
req=B/'R051_A1_origin_requirements/additional_origin_requirements.csv';rows=list(csv.DictReader(req.open(encoding='utf-8-sig')));codes=sorted({r['pref_code'] for r in rows});assert len(rows)==26 and len(codes)==13
state={'state':'waiting_resource_admission','started_jst':now(),'scope_prefectures':47,'additional_prefecture_origin_rows':26,'queue':codes,'completed_prefectures':[],'runtime_sha256':{str(p):sha(p) for p in R.glob('*.py')},'requirements_sha256':sha(req),'output_type':'delta_and_control_rows_not_complete_A1_matrices','source_frame_finalized':False,'main_runtime_modified':False}
def save():state['checked_jst']=now();STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
def unchanged():
    assert sha(req)==state['requirements_sha256']
    for p,h in state['runtime_sha256'].items():assert sha(Path(p))==h
save();env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
try:
    for code in codes:
        state.update(state='waiting_resource_admission',pref_code=code);save()
        while True:
            ram=psutil.virtual_memory().available;c=shutil.disk_usage(B.resolve()).free;d=shutil.disk_usage(DISK).free;state.update(available_ram=ram,C_free=c,D_free=d);save()
            if ram>=9*1024**3 and c>=2500*1024**2 and d>=8*1024**3:break
            time.sleep(5)
        unchanged();state.update(state='running_delta_prefecture',phase_started_jst=now());save()
        command=[sys.executable,str(R/'profile_self.py'),str(R/'R052_delta_worker.py'),str(O/('pref'+code+'_self_profile.json')),code]
        with (O/('pref'+code+'.log')).open('w',encoding='utf-8') as log:
            child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));state['child_pid_not_liveness_proof']=child.pid;save();low=0
            while child.poll() is None:
                time.sleep(5);ram=psutil.virtual_memory().available;c=shutil.disk_usage(B.resolve()).free;d=shutil.disk_usage(DISK).free;state.update(available_ram=ram,C_free=c,D_free=d);save()
                low=low+1 if ram<4*1024**3 or c<1500*1024**2 or d<4*1024**3 else 0
                if low>=2:child.terminate();child.wait();state['own_child_guard_terminated']=True;save();break
            state['last_child_exit_code']=child.returncode;save()
            if child.returncode:raise RuntimeError('Delta child failed: '+code+'; preserve, no automatic relaunch')
        proof=json.loads((O/('pref'+code)/'job.json').read_text(encoding='utf-8'));assert proof['state']=='completed_additional_origin_delta_not_full_A1_matrix'
        if code=='03':assert proof['control_comparison']['state']=='geometry_and_both_control_sparse_rows_exactly_reproduced'
        state['completed_prefectures'].append(code);save();print(json.dumps({'completed_delta_regions':len(state['completed_prefectures']),'total_delta_regions':13,'last':code,'old_controls':proof['control_comparison']['state']}),flush=True)
    unchanged();state.update(state='completed_all26_delta_origin_rows_not_full_A1_dataset',finished_jst=now(),full_A1_matrices_completed=False,A1_optimization_completed=False);save();print('all26 additional origin rows computed; full derivation still required',flush=True)
except BaseException as exc:state.update(state='failed_outputs_preserved',error=repr(exc));save();raise

