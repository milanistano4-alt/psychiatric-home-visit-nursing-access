"""Execute the original frozen producer with an explicit memory-only adapter.

The producer/helper files and numerical statements are executed unchanged.
The adapter changes NPZ field lifetimes and releases statically dead temporary
arrays before CSR construction. It records separate provenance in the job.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import ast,gc,hashlib,json,os,runpy,sys
import numpy as np
from lazy_numeric_npz import graph_load_adapter

BASE=Path(__file__).resolve().parent
ROOT=next(p for p in [BASE,*BASE.parents] if p.name=='codex' and (p/'R023_runtime').is_dir())
FROZEN=ROOT/'R023_runtime'
PRODUCER=FROZEN/'traveltime_national_graph.py'
EXPECTED_PRODUCER='6693071466232ea121d677645355d4cc103d5c72d60c001deb88c87c44c2482e'
EXPECTED_HELPER='e54d17cf3b3c0792cf9df26f1394e2f422a11888e160c49187499e3107bbebc9'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def dead_globals_certificate(source):
    """Prove the named temporaries are never loaded after CSR construction."""
    tree=ast.parse(source);points=[(i,node) for i,node in enumerate(tree.body)
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='Gc' for t in node.targets)
        and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name)
        and node.value.func.id=='directed_time_csr']
    if len(points)!=1:raise ValueError('Unreviewed producer CSR location')
    i,node=points[0]
    after=ast.Module(body=tree.body[i+1:],type_ignores=[])
    loaded={x.id for x in ast.walk(after) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}
    names=['inb','ke','newid','Lm','fs','bs','ow']
    if set(names)&loaded:raise ValueError('Temporary variables are not dead')
    return {'csr_call_line':node.lineno,'statically_dead_names':names,'normalized_source_text_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest()}


def make_release_adapter(original,certificate):
    names=certificate['statically_dead_names'];before={'inb','ke','newid'}
    def build(*args,**kwargs):
        frame=sys._getframe(1)
        if Path(frame.f_code.co_filename).resolve()!=PRODUCER.resolve():
            return original(*args,**kwargs)
        namespace=frame.f_globals
        for name in before:namespace.pop(name,None)
        gc.collect()
        result=original(*args,**kwargs)
        # The argument dictionary owns the still-required arrays during the call.
        # Only release their producer globals after the numerical helper returns.
        for name in names:namespace.pop(name,None)
        gc.collect()
        return result
    return build


def main():
    args=sys.argv[1:]
    if len(args)!=6:raise ValueError('Expected pilot cfg population master NEW_OUT launch_receipt')
    pilot,cfg,population,master,out,launch=args
    if Path(out).exists() or Path(launch).exists():raise FileExistsError('Preserve existing attempts; no silent overwrite')
    assert sha(PRODUCER)==EXPECTED_PRODUCER and sha(FROZEN/'graph_integrity.py')==EXPECTED_HELPER
    source=PRODUCER.read_text(encoding='utf-8');certificate=dead_globals_certificate(source)
    graph=Path(os.environ['PVN_GRAPH']).resolve();registry=[];original=np.load
    sys.path.insert(0,str(FROZEN))
    import graph_integrity
    old_builder=graph_integrity.directed_time_csr
    now=lambda:datetime.now(timezone(timedelta(hours=9))).isoformat()
    adapter={'started_jst':now(),'state':'running','source_producer_sha256':EXPECTED_PRODUCER,
             'numerical_helper_sha256':EXPECTED_HELPER,'adapter_launcher_sha256':sha(__file__),
             'lazy_loader_sha256':sha(BASE/'lazy_numeric_npz.py'),'graph_sha256':sha(graph),
             'dead_global_certificate':certificate,'out_directory':str(out),
             'semantic_scope':'Loading lifetime only; original frozen producer and helper numerical statements unchanged.',
             'clinical_or_national_validation':False}
    lp=Path(launch);lp.parent.mkdir(parents=True,exist_ok=True)
    def save():lp.write_text(json.dumps(adapter,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    try:
        np.load=graph_load_adapter(graph,original,registry)
        graph_integrity.directed_time_csr=make_release_adapter(old_builder,certificate)
        sys.argv=[str(PRODUCER),pilot,cfg,population,master,out]
        runpy.run_path(str(PRODUCER),run_name='__main__')
        assert len(registry)==1 and sha(PRODUCER)==EXPECTED_PRODUCER
        jpath=Path(out)/'job.json';j=json.loads(jpath.read_text(encoding='utf-8'))
        assert j['state']=='completed_static_graph_scenario'
        adapter.update(state='completed_original_producer_with_memory_adapter',finished_jst=now(),
                       field_read_counts=registry[0].read_count);save()
        j['execution_memory_adapter']={'receipt':str(lp),'receipt_sha256':sha(lp),
            'adapter_launcher_sha256':adapter['adapter_launcher_sha256'],
            'lazy_loader_sha256':adapter['lazy_loader_sha256'],
            'original_numerical_producer_unchanged':True,
            'warning':'Additional execution provenance; equivalence to previous outputs must be verified separately.'}
        jpath.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8')
    except BaseException as exc:
        adapter.update(state='failed_preserved_outputs',error=repr(exc),finished_jst=now());save();raise
    finally:
        np.load=original;graph_integrity.directed_time_csr=old_builder
        for z in registry:z.close()


if __name__=='__main__':main()
