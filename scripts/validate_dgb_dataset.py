"""Validate compact DGB V2 data (offline; optionally verify against original RoBAS ZIP).

This intentionally does NOT validate bearing feasibility, expected solver convergence,
actual contact/stiffness/life results, or material/fit suitability.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]/'DGB_Design_Dataset'
VARIABLES={'Dw_mm','Z','Dpw_mm','fi','fo'}
MAT='RoBAS_Resources/Resource/materialDB.csv'
LUB='RoBAS_Resources/Resource/lubricantDB.csv'
MODEL='RoBAS_Resources/Data/DGBData.db'
MATERIAL_MAP={
  'elastic_modulus_pa':'elsaModules(Pa)',
  'density_kg_m3':'density(kg/m3)',
  'thermal_conductivity_w_m_k':'heatConductivity(w/m/k)',
  'thermal_expansion_1_k':'linearExpan(1/k)',
  'poisson_ratio':'poisson',
  'specific_heat_j_kg_k':'specificHeat'
}
LUB_MAP={
  'density0_source_value':'density0',
  'temperature_1_c':'t1(degC)',
  'kinematic_viscosity_1_m2_s':'v1(m^2/s)',
  'temperature_2_c':'t2(degC)',
  'kinematic_viscosity_2_m2_s':'v2(m^2/s)',
  'density_slope_source_value':'slopeDensity',
  'specific_heat0_j_kg_c':'specificHeat0(J/kg/degC)',
  'specific_heat_slope_source_value':'slopeCp'
}

def digest(b):return hashlib.sha256(b).hexdigest()
def fail(msg):raise ValueError(msg)

def load(path):
  return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def offline(cases,requests,schema):
  Draft202012Validator.check_schema(schema)
  validator=Draft202012Validator(schema)
  for typ, rows in [('case',cases),('request',requests)]:
    for idx,row in enumerate(rows,1):
      errors=list(validator.iter_errors(row))
      if errors:fail(f'{typ} line {idx}: '+errors[0].message)
  if len(cases)!=len(requests):fail('design/request count differs')
  cmap={c['case_id']:c for c in cases}
  rmap={r['case_id']:r for r in requests}
  if len(cmap)!=len(cases) or len(rmap)!=len(requests) or cmap.keys()!=rmap.keys():
    fail('case_id uniqueness or join mismatch')
  if len(set(r['request_id'] for r in requests))!=len(requests):fail('duplicate request id')
  if len(set(r['text'] for r in requests))!=len(requests):fail('duplicate natural language request')
  for cid,c in cmap.items():
    d=c['dimensions']; op=c['operating']; en=c['engineering'];data=c['robas_data']
    if not (0<d['d_mm']<d['D_mm'] and d['B_mm']>0):fail(f'{cid}: invalid envelope')
    if c['bearing']['reference_model']!=data['model_record']['model']:fail(f'{cid}: model key mismatch')
    if any(d[k]!=data['model_record'][k] for k in d):fail(f'{cid}: catalog dimension mismatch')
    if op['inner_speed_rpm']==op['outer_speed_rpm']:fail(f'{cid}: zero relative rotation outside intended test family')
    if op['axial_load_n']==0 and '不适用' not in op['axial_load_direction']:fail(f'{cid}: unexpected axial direction')
    used={en[k] for k in ('inner_ring_material','outer_ring_material','ball_material','cage_material')}
    if used != set(data['materials']):fail(f'{cid}: actual material snapshot mismatch')
    if {en['lubricant']}!=set(data['lubricants']):fail(f'{cid}: lubricant snapshot mismatch')
    opt=c['optimization']; active=set(opt['variables']); locked=set(opt['locked']); bounded=set(opt['bounds'])
    if active & locked or (active|locked)!=VARIABLES or not bounded<=active:
      fail(f'{cid}: inconsistent optimization variables/locked/bounds')
    for key,b in opt['bounds'].items():
      if b['min']>=b['max']:fail(f'{cid}: bad bound {key}')
    if c['quality']['scenario_origin']!='synthetic':fail(f'{cid}: unexpected provenance')
    if not c['quality']['catalog_verified'] or c['quality']['engineering_reviewed'] or c['quality']['solver_verified']:
      fail(f'{cid}: unverifiable quality claims')
    text=rmap[cid]['text']
    must=[c['bearing']['reference_model'],str(d['d_mm']),str(d['D_mm']),str(d['B_mm']),str(op['inner_speed_rpm']),
          str(op['radial_load_n']),str(op['axial_load_n']),str(op['temperature_c']),en['inner_ring_material'],
          en['ball_material'],en['cage_material'],en['cage_type'],en['lubricant'],en['clearance_group'],
          en['shaft_fit'],en['housing_fit']]
    if any(s not in text for s in must):fail(f'{cid}: request missing design field text')
    for k,v in opt['locked'].items():
      if k not in text or str(v) not in text:fail(f'{cid}: lock missing from request')
    for k,b in opt['bounds'].items():
      if (('Dw' if k=='Dw_mm' else k) not in text or f"{b['min']:g}" not in text or f"{b['max']:g}" not in text):
        fail(f'{cid}: bounds missing from request')
    for con in c['requirements']['constraints']:
      if f"{con['value']:g}" not in text:fail(f'{cid}: numeric target omitted')
    if not all('csv_line' in value for value in data['materials'].values()):fail(f'{cid}: material evidence missing')
  return len(cases),len(requests)

def verified_catalog(cases,archive):
  with zipfile.ZipFile(archive) as z:
    mb,lb,db=(z.read(p) for p in (MAT,LUB,MODEL))
  archive_sha=digest(archive.read_bytes())
  mats=list(enumerate(csv.DictReader(io.StringIO(mb.decode('utf-8-sig'))),start=2))
  lubs=list(enumerate(csv.DictReader(io.StringIO(lb.decode('utf-8-sig'))),start=2))
  with tempfile.NamedTemporaryFile(suffix='.db') as t:
    t.write(db);t.flush();con=sqlite3.connect(t.name)
    model_results={c['bearing']['reference_model']:con.execute('select model,d,Dd,B,rsmin from model where model=?',(c['bearing']['reference_model'],)).fetchall() for c in cases}
    ref_z={c['bearing']['reference_model']:con.execute('select Z from "主参数" where model=?',(c['bearing']['reference_model'],)).fetchall() for c in cases}
    con.close()
  for c in cases:
    cid=c['case_id'];meta=c['robas_data']['sources'];m=c['robas_data']['model_record']
    if meta['resource_archive_sha256']!=archive_sha:fail(f'{cid}: RoBAS archive SHA mismatch')
    if meta['materials']['sha256']!=digest(mb) or meta['lubricants']['sha256']!=digest(lb) or meta['model']['sha256']!=digest(db):
      fail(f'{cid}: catalog file SHA mismatch')
    matches=model_results[c['bearing']['reference_model']]
    if len(matches)!=1 or tuple(matches[0]) != (m['model'],m['d_mm'],m['D_mm'],m['B_mm'],m['rsmin_mm']):
      fail(f'{cid}: RoBAS model row mismatch')
    if 'Z' in c['optimization']['locked']:
      zrows=ref_z[c['bearing']['reference_model']]
      if len(zrows)!=1 or int(zrows[0][0])!=c['optimization']['locked']['Z']:
        fail(f'{cid}: Z lock not matched in RoBAS 主参数 table')
    for name,values in c['robas_data']['materials'].items():
      found=[(i,row) for i,row in mats if row['materialName']==name]
      if len(found)!=1 or found[0][0]!=values['csv_line']:fail(f'{cid}: unknown material or wrong csv line: {name}')
      row=found[0][1]
      for field,key in MATERIAL_MAP.items():
        if not math.isclose(float(row[key]),values[field],rel_tol=1e-12,abs_tol=1e-15):
          fail(f'{cid}: material physical property {name} {field} mismatched')
    for name,values in c['robas_data']['lubricants'].items():
      found=[(i,row) for i,row in lubs if row['oilName']==name]
      if len(found)!=1 or found[0][0]!=values['csv_line']:fail(f'{cid}: unknown lubricant or wrong csv line: {name}')
      row=found[0][1]
      for field,key in LUB_MAP.items():
        if not math.isclose(float(row[key]),values[field],rel_tol=1e-12,abs_tol=1e-15):
          fail(f'{cid}: lubricant physical property {name} {field} mismatched')
  return {'verified_models':len(set(c['bearing']['reference_model'] for c in cases)),
          'verified_materials':len(set(k for c in cases for k in c['robas_data']['materials'])),
          'verified_lubricants':len(set(k for c in cases for k in c['robas_data']['lubricants']))}


def main():
  p=argparse.ArgumentParser()
  p.add_argument('--robas-archive',type=Path,help='RoBAS_Resources.zip to independently recheck SHA, DB and CSV rows')
  args=p.parse_args()
  cases=load(ROOT/'data'/'design_cases.jsonl');requests=load(ROOT/'data'/'user_requests.jsonl')
  schema=json.loads((ROOT/'schema'/'DGBCase_v2.schema.json').read_text(encoding='utf-8'))
  n,m=offline(cases,requests,schema)
  with (ROOT/'review'/'case_review.csv').open(encoding='utf-8-sig',newline='') as f:
    review=list(csv.DictReader(f))
  if len(review)!=n or {x['case_id'] for x in review}!={x['case_id'] for x in cases}:
    fail('review CSV mismatch')
  print(f'STRUCTURE_AND_CROSSFILE_PASS: {n} design cases, {m} natural-language requests, {len(review)} review rows')
  print('OBJECTIVES:',dict(Counter(x['requirements']['objective'] for x in cases)))
  if args.robas_archive:
    print('CATALOG_EXACT_MATCH_PASS:',verified_catalog(cases,args.robas_archive))
  else:
    print('CATALOG_NOT_RECHECKED: pass --robas-archive for independent original RoBAS matching')
  print('ENGINEERING_APPROVED=0; SOLVER_VERIFIED=0; performance constraints are unverified synthetic goals')

if __name__=='__main__':main()
