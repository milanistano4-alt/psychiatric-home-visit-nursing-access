"""Explicit read-only numeric cache and AST-gated disk-backed prefix sums."""
from pathlib import Path
import ast,hashlib,json,sys
import numpy as np

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

class MappedNumericNPZ:
    def __init__(self,manifest_path,original_load,verify=True):
        self.manifest_path=Path(manifest_path);self.meta=json.loads(self.manifest_path.read_text(encoding='utf-8'))
        if self.meta['state']!='complete_byte_verified_cache':raise ValueError('Incomplete cache')
        self.files=list(self.meta['fields']);self.original_load=original_load;self.read_count={};self.closed=False
        if verify:
            for field in self.meta['fields'].values():
                if digest(field['path'])!=field['npy_sha256']:raise ValueError('Cached NPY changed')
    def __getitem__(self,key):
        if self.closed:raise ValueError('Cache archive is closed')
        if key not in self.meta['fields']:raise KeyError(key)
        info=self.meta['fields'][key];a=self.original_load(info['path'],mmap_mode='r',allow_pickle=False)
        if a.dtype.hasobject or a.dtype.str!=info['dtype'] or list(a.shape)!=info['shape']:raise ValueError('Cache numeric schema changed')
        if a.flags.writeable:raise ValueError('Cache must be read-only')
        self.read_count[key]=self.read_count.get(key,0)+1
        return a
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def graph_load_adapter(graph_path,manifest_path,original_load,registry):
    graph=Path(graph_path).resolve();meta=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if Path(meta['source_npz']).resolve()!=graph:raise ValueError('Cache is for another graph')
    if digest(graph)!=meta['source_npz_sha256']:raise ValueError('Original graph changed')
    def load(file,*args,**kwargs):
        if isinstance(file,(str,Path)) and Path(file).resolve()==graph:
            if args or kwargs:raise ValueError('Unexpected graph load options')
            result=MappedNumericNPZ(manifest_path,original_load);registry.append(result);return result
        return original_load(file,*args,**kwargs)
    return load

def prefix_certificate(source):
    """Only exactly `newid = np.cumsum(inb) - 1` may use this adapter."""
    tree=ast.parse(source);matches=[]
    expected=ast.parse('newid = np.cumsum(inb) - 1').body[0]
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='newid' for t in node.targets):
            if ast.dump(node,include_attributes=False)!=ast.dump(expected,include_attributes=False):raise ValueError('Unreviewed prefix expression')
            matches.append(node)
    if len(matches)!=1:raise ValueError('Expected one reviewed prefix assignment')
    return {'call_line':matches[0].lineno,'expression':'newid = np.cumsum(inb) - 1','normalized_source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest()}

class PendingMappedPrefix:
    def __init__(self,array,receipt):self.array=array;self.receipt=receipt;self.consumed=False
    def __sub__(self,other):
        if self.consumed or type(other) is not int or other!=1:raise ValueError('Unreviewed use of prefix result')
        self.consumed=True;a=self.array
        for start in range(0,len(a),65536):np.subtract(a[start:start+65536],1,out=a[start:start+65536])
        a.flush();a.flags.writeable=False;self.receipt['subtraction_applied_exactly_once']=True
        self.array=None
        return a

def mapped_cumsum_adapter(original,producer,certificate,scratch,receipts):
    producer=Path(producer).resolve();scratch=Path(scratch);used=False
    def cumsum(a,*args,**kwargs):
        nonlocal used
        frame=sys._getframe(1)
        if Path(frame.f_code.co_filename).resolve()!=producer or frame.f_lineno!=certificate['call_line']:
            return original(a,*args,**kwargs)
        if used or args or kwargs or not isinstance(a,np.ndarray) or a.ndim!=1 or a.dtype!=np.dtype(bool) or frame.f_globals.get('inb') is not a:raise ValueError('Unreviewed prefix invocation')
        used=True
        if scratch.exists():raise FileExistsError('Preserve prior prefix workspace')
        scratch.mkdir(parents=True);p=scratch/'node_prefix.npy'
        dtype=original(np.array([True],dtype=bool)).dtype
        mm=np.lib.format.open_memmap(p,mode='w+',dtype=dtype,shape=a.shape)
        original(a,out=mm);mm.flush()
        receipt={'path':str(p),'shape':list(a.shape),'dtype':dtype.str,'source_boolean_count':int(a.sum()),'subtraction_applied_exactly_once':False}
        receipts.append(receipt)
        return PendingMappedPrefix(mm,receipt)
    return cumsum
