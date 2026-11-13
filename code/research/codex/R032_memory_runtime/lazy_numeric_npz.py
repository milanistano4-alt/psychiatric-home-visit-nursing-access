"""Read-only, uncached NPZ arrays for the frozen graph producer.

Every operation reads the original NPY payload using NumPy's own reader.
Only loading lifetime changes: source values, dtypes, indexing and comparisons
remain NumPy operations. Object arrays are prohibited. No temporary data files.
"""
from pathlib import Path
import zipfile
import numpy as np


class LazyNumericArray:
    def __init__(self, archive, key):
        self.archive=archive
        self.key=key

    def materialize(self):
        with self.archive._zip.open(self.key+'.npy') as stream:
            a=np.lib.format.read_array(stream,allow_pickle=False)
        if a.dtype.hasobject:raise ValueError('Only numeric arrays are supported')
        self.archive.read_count[self.key]=self.archive.read_count.get(self.key,0)+1
        return a

    def __array__(self,dtype=None,copy=None):
        a=self.materialize()
        if dtype is not None:a=np.asarray(a,dtype=dtype)
        return a.copy() if copy is True else a

    def __getitem__(self,item):return self.materialize()[item]
    def __ge__(self,other):return self.materialize()>=other
    def __le__(self,other):return self.materialize()<=other
    def __gt__(self,other):return self.materialize()>other
    def __lt__(self,other):return self.materialize()<other
    def __eq__(self,other):return self.materialize()==other
    def __ne__(self,other):return self.materialize()!=other


class LazyNumericNPZ:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self._zip=zipfile.ZipFile(self.path)
        self.files=[s[:-4] for s in self._zip.namelist() if s.endswith('.npy')]
        if len(self.files)!=len(set(self.files)):raise ValueError('Duplicate NPZ fields')
        self.read_count={}

    def __getitem__(self,key):
        if key not in self.files:raise KeyError(key)
        return LazyNumericArray(self,key)

    def close(self):self._zip.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def graph_load_adapter(graph_path, original_load, registry):
    """Intercept exactly the declared graph; delegate every other NumPy load."""
    graph=Path(graph_path).resolve()
    def load(file,*args,**kwargs):
        if isinstance(file,(str,Path)) and Path(file).resolve()==graph:
            if args or kwargs:raise ValueError('Unexpected options for the reviewed graph loader')
            result=LazyNumericNPZ(graph);registry.append(result);return result
        return original_load(file,*args,**kwargs)
    return load
