"""Stable content hashes for a file or a directory-backed Parquet dataset."""
from pathlib import Path
import hashlib,json

def artifact_digest(path):
 p=Path(path)
 if p.is_file():
  with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
 if not p.is_dir():raise FileNotFoundError(p)
 records=[]
 for f in sorted(p.rglob('*.parquet')):
  with f.open('rb') as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
  records.append({'name':f.relative_to(p).as_posix(),'bytes':f.stat().st_size,'sha256':h})
 if not records:raise ValueError('No Parquet chunks in completed dataset')
 return hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
