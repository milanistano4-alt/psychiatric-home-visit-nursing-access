"""Self-sampled Python RSS around an unchanged target script; no PID guessing."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,os,runpy,sys,threading,time
import psutil

def main():
    target,output,*args=sys.argv[1:];p=Path(output)
    if p.exists():raise FileExistsError('Profile receipt exists; no overwrite')
    stop=threading.Event();process=psutil.Process(os.getpid())
    result={'state':'running','pid_inside_python':os.getpid(),'target_script':target,
            'started_jst':datetime.now(timezone(timedelta(hours=9))).isoformat(),
            'peak_self_sampled_rss':0,'minimum_global_available':psutil.virtual_memory().available,
            'sample_count':0,'sampling_interval_seconds':.1}
    def sample():
        while not stop.is_set():
            result['peak_self_sampled_rss']=max(result['peak_self_sampled_rss'],process.memory_info().rss)
            result['minimum_global_available']=min(result['minimum_global_available'],psutil.virtual_memory().available)
            result['sample_count']+=1;stop.wait(.1)
    worker=threading.Thread(target=sample,daemon=True);worker.start()
    try:
        sys.argv=[target,*args];sys.path.insert(0,str(Path(target).resolve().parent));runpy.run_path(target,run_name='__main__');result['state']='completed'
    except BaseException as exc:result.update(state='failed',error=repr(exc));raise
    finally:
        stop.set();worker.join();result['finished_jst']=datetime.now(timezone(timedelta(hours=9))).isoformat()
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2),encoding='utf-8')

if __name__=='__main__':main()
