from pathlib import Path
from datetime import datetime,timezone,timedelta
import sys,zipfile,io,re,json,hashlib
from decimal import Decimal
import pandas as pd,numpy as np
sys.path.insert(0,str(Path('research/PHVN-20261024/scripts').resolve()));from audit_population import dbf_rows,read_text,scaled
out=Path('research/codex/R021_inputs');out.mkdir(exist_ok=False);src=Path('research/raw_research/mesh500r6/500m_mesh_2024_SHP.zip');h=hashlib.sha256(src.read_bytes()).hexdigest();parts=[];stats=[];allkeys=[]
with zipfile.ZipFile(src) as outer:
 members=[(int(m[1]),name) for name in outer.namelist() if (m:=re.search(r'_([0-9]{2})_SHP\.zip$',name))];assert sorted(k for k,n in members)==list(range(1,48))
 for pc,name in sorted(members):
  rawzip=outer.read(name)
  with zipfile.ZipFile(io.BytesIO(rawzip)) as z:
   dbfs=[n for n in z.namelist() if n.endswith('.dbf')];assert len(dbfs)==1;rows=[];total=0
   with z.open(dbfs[0]) as f:
    it=dbf_rows(f);fields,expected=next(it);cols=[n for n in fields if n in ('MESH_ID','SHICODE','PTN_2020','HITOKU2025','GASSAN2025') or n.endswith('_2025')]
    for raw in it:
     r={n:read_text(raw,fields[n]) for n in cols};assert re.fullmatch(r'\d{9}',r['MESH_ID']);total+=scaled(raw,fields['PTN_2020']);rows.append(r)
   assert len(rows)==expected
   df=pd.DataFrame(rows);df['pref_code']=f'{pc:02d}'
   for n in cols:
    if n.startswith('PT'):df[n]=pd.to_numeric(df[n],errors='raise')
   m=df.MESH_ID;h9=m.str[8].astype(int);df['lat']=m.str[:2].astype(int)/1.5+m.str[4].astype(int)*5/60+m.str[6].astype(int)*30/3600+h9.isin([3,4])*15/3600+7.5/3600;df['lon']=m.str[2:4].astype(int)+100+m.str[5].astype(int)*7.5/60+m.str[7].astype(int)*45/3600+h9.isin([2,4])*22.5/3600+11.25/3600
   assert not df.duplicated(['pref_code','MESH_ID']).any();parts.append(df);stats.append({'pref_code':f'{pc:02d}','rows':len(df),'population_2020_scaled_10000':total,'inner_zip_sha256':hashlib.sha256(rawzip).hexdigest()});print(json.dumps(stats[-1]),flush=True)
m=pd.concat(parts,ignore_index=True);assert len(m)==466792 and m.MESH_ID.nunique()==465895 and not m.duplicated(['pref_code','MESH_ID']).any();assert abs(sum(s['population_2020_scaled_10000'] for s in stats)/10000-126146099)<.01
# Coordinate construction must agree with previously received meshes, up to numerical precision.
g=pd.read_parquet('research/pilots/soya_nemuro_mesh/mesh_geom.parquet');check=m.groupby('MESH_ID',as_index=False)[['lat','lon']].mean().merge(g[['MESH_ID','lat','lon']].assign(MESH_ID=lambda x:x.MESH_ID.astype(str)),on='MESH_ID',suffixes=('_new','_old'),validate='one_to_one');err=float(np.max(np.abs(check[['lat_new','lon_new']].to_numpy()-check[['lat_old','lon_old']].to_numpy())));assert len(check)==len(g) and err<1e-8
p=out/'mesh500.parquet';m.to_parquet(p,index=False);v={'state':'completed','jst':datetime.now(timezone(timedelta(hours=9))).isoformat(),'source':str(src),'source_sha256':h,'prefectures':47,'rows':len(m),'unique_geometry_ids':m.MESH_ID.nunique(),'population2020':sum(s['population_2020_scaled_10000'] for s in stats)/10000,'component_key':'pref_code,MESH_ID; no cross-prefecture population deduplication','centers':'analytical center of official 9-digit 500m mesh; agrees with all received Soya/Nemuro geometries within1e-8degrees','coordinate_max_absolute_difference_degrees':err,'output_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'prefecture_audit':stats,'national_access_results_computed':False};(out/'manifest.json').write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in v.items() if k!='prefecture_audit'}),flush=True)
