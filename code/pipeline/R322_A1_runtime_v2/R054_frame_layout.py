"""Reconstruct A1 sites/origins under the pinned old population selection policy."""
import numpy as np,pandas as pd
from scipy.spatial import cKDTree

def sphere(lat,lon):
    a=np.radians(np.asarray(lat,float));b=np.radians(np.asarray(lon,float));return np.c_[np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)]
def mesh500(lat,lon):
    p=np.floor(lat*1.5).astype(int);u=np.floor(lon-100).astype(int);q=np.floor((lat*1.5-p)*8).astype(int);v=np.floor((lon-100-u)*8).astype(int);r=np.floor(((lat*1.5-p)*8-q)*10).astype(int);w=np.floor(((lon-100-u)*8-v)*10).astype(int);a=np.floor((((lat*1.5-p)*8-q)*10-r)*2).astype(int);b=np.floor((((lon-100-u)*8-v)*10-w)*2).astype(int)
    return np.array([f'{P:02d}{U:02d}{Q}{V}{R}{W}{1+A*2+C}' for P,U,Q,V,R,W,A,C in zip(p,u,q,v,r,w,a,b)])
def center(code):
    c=str(code);h=int(c[8]);return (int(c[:2])/1.5+int(c[4])*5/60+int(c[6])*30/3600+(h in (3,4))*15/3600+7.5/3600,int(c[2:4])+100+int(c[5])*7.5/60+int(c[7])*45/3600+(h in (2,4))*22.5/3600+11.25/3600)

def build(master,comp,geom,candidates,code):
    L=master.copy();L['lat']=pd.to_numeric(L.lat,errors='coerce');L['lon']=pd.to_numeric(L.lon,errors='coerce');known=np.isfinite(L.lat)&np.isfinite(L.lon);D=comp[comp.in_pilot];assert set(D.pref_code)=={code}
    west,east,south,north=D.lon.min(),D.lon.max(),D.lat.min(),D.lat.max();own=L.pref_code.eq(code)
    S=L[known&(own|(L.lon.between(west-.55,east+.55)&L.lat.between(south-.55,north+.55)))].copy();d,_=cKDTree(sphere(D.lat,D.lon)).query(sphere(S.lat,S.lon));km=2*6371000*np.arcsin(np.clip(d/2,0,1))/1000;S=S[(km<=41)|S.pref_code.eq(code)].copy()
    S=S[['id','pref','lat','lon','位置の出どころ','station_key','pref_code']].rename(columns={'位置の出どころ':'geo_src'});S['kind']='station'
    C=candidates[candidates.pref_code.eq(code)].copy();G=geom.set_index(geom.MESH_ID.astype(str));assert set(C.omesh)<=set(G.index)
    Cd=pd.DataFrame({'id':C.candidate_id,'pref':L.loc[own,'pref'].iloc[0],'lat':G.loc[C.omesh,'lat'].to_numpy(),'lon':G.loc[C.omesh,'lon'].to_numpy(),'geo_src':'mesh','station_key':'','pref_code':code,'kind':'candidate'})
    sites=pd.concat([S,Cd],ignore_index=True);sites['omesh']=mesh500(sites.lat.to_numpy(),sites.lon.to_numpy());O=sites.groupby('omesh').agg(has_station=('kind',lambda x:x.eq('station').any()),n_sites=('kind','size')).reset_index();O[['lat','lon']]=[center(m) for m in O.omesh];O['kind']=np.where(O.has_station,'station','candidate')
    sites['o']=sites.omesh.map({m:k for k,m in enumerate(O.omesh)}).astype(np.int32);sites['official_in_pilot']=sites.kind.eq('station')&sites.pref_code.eq(code);sites['owner_pref_codes']=code;sites['area30_km2']=np.nan
    budget=int(own.sum());missing=int((own&~known).sum());known_owned=int(sites.official_in_pilot.sum());assert known_owned==budget-missing
    return sites,O,{'facility_frame_owned_total':budget,'facility_frame_missing_coordinates':missing,'facility_frame_missing_coordinates_all':int((~known).sum()),'known_owned_sites_included':known_owned}
