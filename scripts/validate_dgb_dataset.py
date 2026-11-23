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
from generate_dgb_cases_v2 import assemble_request, screen_synthetic_case, CASES
from collections import Counter
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]/'DGB_Design_Dataset'
VARIABLES={'Dw_mm','Z','Dpw_mm','fi','fo'}
FOCUSED_MODEL_COUNTS={'6205':30,'6204':15,'6206':15,'6005':10,'6305':10}
FOCUSED_OBJECTIVES={'minimize_power_loss','maximize_L10h','minimize_temperature_rise','minimize_peak_contact_pressure','maximize_radial_stiffness'}
STYLES={'工程技术交底','日常口语','项目委托','参数清单','目标先行','简明压缩','约束先行','现场说明','设计复核','工况先行'}
MAT='RoBAS_Resources/Resource/materialDB.csv'
LUB='RoBAS_Resources/Resource/lubricantDB.csv'
MODEL='RoBAS_Resources/Data/DGBData.db'
PERFORMANCE='RoBAS_Resources/Data/bearing.db'
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
  if any(r.get('language_style') not in STYLES for r in requests):fail('unknown language style')
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
    # These 80 texts are deterministic generated reference utterances: strict
    # reproduction catches ANY changed numeric token, unit, inequality or Z lock.
    # The former substring checks alone accepted Fr=300 -> Fr=3000 and <= -> >=.
    index=int(cid.split('-')[-1])
    if index<1 or index>len(CASES):fail(f'{cid}: unexpected case index')
    style,rendered=assemble_request(c,index)
    if rmap[cid]['language_style']!=style or text!=rendered:
      fail(f'{cid}: natural language differs from exact case rendering (value/unit/constraint/optimization mismatch)')
    check_reference_screen(c)
    must=[c['bearing']['reference_model'],str(d['d_mm']),str(d['D_mm']),str(d['B_mm']),str(op['inner_speed_rpm']),
          str(op['radial_load_n']),str(op['axial_load_n']),str(op['temperature_c']),en['inner_ring_material'],
          en['ball_material'],en['cage_material'],en['cage_type'],en['lubricant'],en['clearance_group'],
          en['shaft_fit'],en['housing_fit']]
    if any(s not in text for s in must):fail(f'{cid}: request missing design field text')
    for k,v in opt['locked'].items():
      if k not in text or str(v) not in text:fail(f'{cid}: lock missing from request')
    variable_words={'Dw_mm':'Dw','Z':'Z','Dpw_mm':'Dpw','fi':'fi','fo':'fo'}
    for k,b in opt['bounds'].items():
      if (variable_words[k] not in text or f"{b['min']:g}" not in text or f"{b['max']:g}" not in text):
        fail(f'{cid}: bounds missing from request')
    metric_tokens={'L10h':'L10h','power_loss_w':'功耗','temperature_rise_c':'温升','peak_contact_pressure_mpa':'接触压力'}
    for con in c['requirements']['constraints']:
      if (f"{con['value']:g}" not in text or metric_tokens[con['metric']] not in text):
        fail(f'{cid}: numeric target or metric omitted')
    objective_tokens={'minimize_power_loss':'功耗','maximize_L10h':'寿命',
       'minimize_temperature_rise':'温升','minimize_peak_contact_pressure':'接触',
       'maximize_radial_stiffness':'刚度'}
    if objective_tokens[c['requirements']['objective']] not in text:fail(f'{cid}: objective omitted')
    if not ('外圈' in text and '固定' in text and '顺时针' in text and '竖直向下' in text):
      fail(f'{cid}: rotation or load direction missing')
    if any(not (100 <= len(x['text']) <= 1000) for x in [rmap[cid]]):
      fail(f'{cid}: suspicious natural-language length')
    if not all('csv_line' in value for value in data['materials'].values()):fail(f'{cid}: material evidence missing')
  return len(cases),len(requests)

def check_reference_screen(c):
  cid=c['case_id'];perf=c['robas_data']['reference_performance'];s=c['quality']['reference_screen']
  if any(perf[k]<=0 for k in perf):fail(f'{cid}: invalid reference performance')
  n=c['operating']['inner_speed_rpm'];fr=c['operating']['radial_load_n']
  if abs(s['speed_ratio']-round(n/perf['nmax_rpm'],5))>1e-8:fail(f'{cid}: speed ratio inconsistent')
  if abs(s['fr_to_reference_C0_ratio']-round(fr/(1000*perf['C0_kN']),5))>1e-8:fail(f'{cid}: static ratio inconsistent')
  life=[x['value'] for x in c['requirements']['constraints'] if x['metric']=='L10h']
  life_ratio=round(fr*(60*n*life[0]/1e6)**(1/3)/(perf['C_kN']*1000),5) if life else None
  if s['life_min_C_ratio'] != life_ratio:fail(f'{cid}: life reference ratio inconsistent')
  if s['speed_ratio']>0.90001 or s['fr_to_reference_C0_ratio']>0.47001 or (life_ratio is not None and life_ratio>0.75001):
      fail(f'{cid}: severe reference screen red flag')
  if ('minimize_temperature_rise'==c['requirements']['objective'] or any(x['metric']=='temperature_rise_c' for x in c['requirements']['constraints'])):
      if 'ambient_temperature_c' not in c['operating']:fail(f'{cid}: temperature-rise reference missing')
      if c['operating']['ambient_temperature_c']>=c['operating']['temperature_c']:fail(f'{cid}: reference ambient not below initial estimated bearing temperature')

def verified_catalog(cases,archive):
  with zipfile.ZipFile(archive) as z:
    mb,lb,db,pb=(z.read(p) for p in (MAT,LUB,MODEL,PERFORMANCE))
  archive_sha=digest(archive.read_bytes())
  mats=list(enumerate(csv.DictReader(io.StringIO(mb.decode('utf-8-sig'))),start=2))
  lubs=list(enumerate(csv.DictReader(io.StringIO(lb.decode('utf-8-sig'))),start=2))
  with tempfile.NamedTemporaryFile(suffix='.db') as t:
    t.write(db);t.flush();con=sqlite3.connect(t.name)
    model_results={c['bearing']['reference_model']:con.execute('select model,d,Dd,B,rsmin from model where model=?',(c['bearing']['reference_model'],)).fetchall() for c in cases}
    ref_z={c['bearing']['reference_model']:con.execute('select Dw,Z,Dwp from "主参数" where model=?',(c['bearing']['reference_model'],)).fetchall() for c in cases}
    con.close()
  with tempfile.NamedTemporaryFile(suffix='.db') as t:
    t.write(pb);t.flush();pc=sqlite3.connect(t.name)
    perf_results={c['bearing']['reference_model']:pc.execute('SELECT d,D_,B,C,C0,nmax FROM T_SKFA01 WHERE Type=?',(c['bearing']['reference_model']+' *',)).fetchall() for c in cases}
    pc.close()
  for c in cases:
    cid=c['case_id'];meta=c['robas_data']['sources'];m=c['robas_data']['model_record']
    if meta['resource_archive_sha256']!=archive_sha:fail(f'{cid}: RoBAS archive SHA mismatch')
    if meta['materials']['sha256']!=digest(mb) or meta['lubricants']['sha256']!=digest(lb) or meta['model']['sha256']!=digest(db) or meta['reference_performance']['sha256']!=digest(pb):
      fail(f'{cid}: catalog file SHA mismatch')
    matches=model_results[c['bearing']['reference_model']]
    if len(matches)!=1 or tuple(matches[0]) != (m['model'],m['d_mm'],m['D_mm'],m['B_mm'],m['rsmin_mm']):
      fail(f'{cid}: RoBAS model row mismatch')
    prs=perf_results[c['bearing']['reference_model']]
    if len(prs)!=1:fail(f'{cid}: missing/ambiguous reference performance')
    row=prs[0]; p=c['robas_data']['reference_performance']
    if tuple(float(x) for x in row[:3]) != (float(m['d_mm']),float(m['D_mm']),float(m['B_mm'])) or any(not math.isclose(float(row[i]),p[k],rel_tol=1e-12) for i,k in [(3,'C_kN'),(4,'C0_kN'),(5,'nmax_rpm')]):
      fail(f'{cid}: mismatched original RoBAS performance catalog row')
    # Source-generated design must correspond to screen-adjusted synthetic scenario.
    idx=int(cid.split('-')[-1]);raw=CASES[idx-1]
    expected,screen=screen_synthetic_case(raw,p)
    op=c['operating']
    if (expected['model']!=c['bearing']['reference_model'] or expected['app']!=c['bearing']['application'] or any(op[k]!=expected[v] for k,v in [('inner_speed_rpm','ni'),('outer_speed_rpm','no'),('radial_load_n','fr'),('axial_load_n','fa'),('temperature_c','temp')])):
      fail(f'{cid}: scenario deviates from reproducible source spec')
    if c['quality']['reference_screen']!=screen:fail(f'{cid}: screen metadata deviates from source spec')
    if 'Z' in c['optimization']['locked']:
      zrows=ref_z[c['bearing']['reference_model']]
      if len(zrows)!=1 or int(zrows[0][1])!=c['optimization']['locked']['Z']:
        fail(f'{cid}: Z lock not matched in RoBAS 主参数 table')
    # Necessary envelope/ball-spacing screen near reference geometry; not
    # a full CAD assembly or a proof that every free Z choice is feasible.
    geo=ref_z[c['bearing']['reference_model']]
    if len(geo)==1:
      dw_ref,z_ref,dp_ref=map(float,geo[0])
      opt=c['optimization']
      dw_hi=opt['bounds'].get('Dw_mm',{}).get('max',dw_ref)
      dp_lo=opt['bounds'].get('Dpw_mm',{}).get('min',dp_ref)
      dp_hi=opt['bounds'].get('Dpw_mm',{}).get('max',dp_ref)
      if dp_lo-dw_hi<=m['d_mm'] or dp_hi+dw_hi>=m['D_mm']:
        fail(f'{cid}: reference-neighborhood rolling element envelope intersects rings')
      if 'Z' in opt['locked'] and dp_lo*math.sin(math.pi/opt['locked']['Z'])<=dw_hi:
        fail(f'{cid}: locked Z conflicts with ball chord clearance')
    elif any(k in c['optimization']['bounds'] for k in ('Dw_mm','Dpw_mm')) or 'Z' in c['optimization']['locked']:
      fail(f'{cid}: reference-dependent geometric restriction without original geometry')
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
  p.add_argument('--focused-80',action='store_true',help='Enforce five-model 80-case study distribution and coverage')
  args=p.parse_args()
  cases=load(ROOT/'data'/'design_cases.jsonl');requests=load(ROOT/'data'/'user_requests.jsonl')
  schema=json.loads((ROOT/'schema'/'DGBCase_v2.schema.json').read_text(encoding='utf-8'))
  n,m=offline(cases,requests,schema)
  if args.focused_80:
    counts=Counter(c['bearing']['reference_model'] for c in cases)
    if counts != FOCUSED_MODEL_COUNTS: fail(f'focused model distribution mismatch: {counts}')
    style_counts=Counter(r['language_style'] for r in requests)
    if style_counts!={k:8 for k in STYLES}:fail(f'focused language style distribution mismatch: {style_counts}')
    for model in FOCUSED_MODEL_COUNTS:
      goals={c['requirements']['objective'] for c in cases if c['bearing']['reference_model']==model}
      if goals!=FOCUSED_OBJECTIVES:fail(f'focused model {model} lacks objective coverage: {goals}')
      if model in {'6005','6305'}:
        if any('Z' in c['optimization']['locked'] or any(k in c['optimization']['bounds'] for k in ('Dw_mm','Dpw_mm')) for c in cases if c['bearing']['reference_model']==model):
          fail(f'focused model {model} has a reference-derived internal geometry without an available 主参数 row')
    print('FOCUSED_80_PROFILE_PASS:',dict(counts))
  with (ROOT/'review'/'case_review.csv').open(encoding='utf-8-sig',newline='') as f:
    review=list(csv.DictReader(f))
  if len(review)!=n or {x['case_id'] for x in review}!={x['case_id'] for x in cases}:
    fail('review CSV mismatch')
  cmap={x['case_id']:x for x in cases};rmap={x['case_id']:x for x in requests}
  for row in review:
    c=cmap[row['case_id']];op=c['operating'];dim=c['dimensions'];screen=c['quality']['reference_screen']
    expected={
      'application':c['bearing']['application'],'reference_model':c['bearing']['reference_model'],
      'd_mm':dim['d_mm'],'D_mm':dim['D_mm'],'B_mm':dim['B_mm'],
      'inner_speed_rpm':op['inner_speed_rpm'],'outer_speed_rpm':op['outer_speed_rpm'],
      'Fr_N':op['radial_load_n'],'Fa_N':op['axial_load_n'],'temperature_c':op['temperature_c'],
      'objective':c['requirements']['objective'],'language_style':rmap[row['case_id']]['language_style'],
      'reference_C_kN':c['robas_data']['reference_performance']['C_kN'],
      'reference_nmax_rpm':c['robas_data']['reference_performance']['nmax_rpm'],
      'speed_to_reference_nmax_ratio':screen['speed_ratio'],
      'fr_to_reference_C0_ratio':screen['fr_to_reference_C0_ratio'],
      'original_speed_rpm':CASES[int(row['case_id'].split('-')[-1])-1]['ni'],
      'original_Fr_N':CASES[int(row['case_id'].split('-')[-1])-1]['fr'],
      'original_Fa_N':CASES[int(row['case_id'].split('-')[-1])-1]['fa'],
      'reference_screen_status':screen['status'],
      'scenario_revised_by_screen':'YES' if screen['scenario_revised'] else 'NO',
    }
    for k,val in expected.items():
      if str(row[k])!=str(val) and not (isinstance(val,(int,float)) and math.isclose(float(row[k]),float(val),rel_tol=1e-12,abs_tol=1e-12)):
        fail(f"review CSV {row['case_id']} mismatch in {k}: {row[k]} != {val}")
    raw=CASES[int(row['case_id'].split('-')[-1])-1]
    if row['optimization_mode']!=raw['opt']:fail('review CSV optimization mode mismatch')
    if (row['thermal_model_status']=='PENDING') != ('ambient_temperature_c' in op):fail('review CSV thermal status mismatch')
    if str(row['min_load_life_C_to_reference_C_ratio']) != str(screen['life_min_C_ratio']) and not (row['min_load_life_C_to_reference_C_ratio']=='' and screen['life_min_C_ratio'] is None):
      fail('review CSV life screen mismatch')

  print(f'STRUCTURE_AND_CROSSFILE_PASS: {n} design cases, {m} natural-language requests, {len(review)} review rows')
  print('OBJECTIVES:',dict(Counter(x['requirements']['objective'] for x in cases)))
  print('LANGUAGE_STYLES:',dict(Counter(x['language_style'] for x in requests)))
  if args.robas_archive:
    print('CATALOG_EXACT_MATCH_PASS:',verified_catalog(cases,args.robas_archive))
  else:
    print('CATALOG_NOT_RECHECKED: pass --robas-archive for independent original RoBAS matching')
  print('ENGINEERING_APPROVED=0; SOLVER_VERIFIED=0; performance constraints are unverified synthetic goals')

if __name__=='__main__':main()
