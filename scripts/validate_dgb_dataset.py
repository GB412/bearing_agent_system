#!/usr/bin/env python3
"""Check DGBCase/v1 structure, dialogue evidence and optional original RoBAS archives.

Usage:
  python scripts/validate_dgb_dataset.py --dataset DGB_Design_Dataset
  python scripts/validate_dgb_dataset.py --dataset DGB_Design_Dataset \
      --robas-archive /private/RoBAS_Resources.zip --source-archive /private/'RoBAS(1).zip' --self-test

Offline validation is not source-database verification. Nothing here approves engineering suitability.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:
    raise SystemExit('Missing dependency: pip install jsonschema') from exc

MATERIAL_COLUMNS = {
    'elastic_modulus':'elsaModules(Pa)', 'density':'density(kg/m3)',
    'thermal_conductivity':'heatConductivity(w/m/k)',
    'linear_expansion':'linearExpan(1/k)', 'poisson_ratio':'poisson',
    'specific_heat':'specificHeat',
}
LUBRICANT_COLUMNS = {
    'density0':'density0', 'temperature_1':'t1(degC)',
    'kinematic_viscosity_1':'v1(m^2/s)', 'temperature_2':'t2(degC)',
    'kinematic_viscosity_2':'v2(m^2/s)', 'density_slope':'slopeDensity',
    'specific_heat0':'specificHeat0(J/kg/degC)', 'specific_heat_slope':'slopeCp',
}
MAT = 'RoBAS_Resources/Resource/materialDB.csv'
LUB = 'RoBAS_Resources/Resource/lubricantDB.csv'
DB = 'RoBAS_Resources/Data/DGBData.db'


def sha(content):
    return hashlib.sha256(content).hexdigest()


def read_jsonl(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    return [json.loads(x, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-JSON number '+x)))
            for x in lines if x.strip()]


def find_params(obj, prefix=''):
    if isinstance(obj, dict):
        if {'value','unit','confirmed','precision','source'}.issubset(obj):
            yield prefix, obj
            return
        for k,v in obj.items():
            yield from find_params(v, f'{prefix}.{k}' if prefix else k)


def prove_user_source(path, obj, user_msgs):
    source = obj.get('source') or {}
    if source.get('kind') != 'user' or not obj['confirmed']:
        return None
    msg_id = source.get('message_id')
    if msg_id not in user_msgs:
        return f'{path}: confirmed user source {msg_id!r} absent from reference dialogue A'
    txt = user_msgs[msg_id]
    val = obj['value']
    if path.startswith('dimensions.'):
        # Must cite the turn where the complete 25×52×15 envelope was explicitly accepted,
        # not the turn that merely named model 6205.
        if not re.search(r'25\s*[×xX*]\s*52\s*[×xX*]\s*15', txt):
            return f'{path}: source {msg_id} does not explicitly support d/D/B=25×52×15'
    elif path == 'operating.outer_speed_rpm' and val == 0:
        if '外圈固定' not in txt and '外圈不动' not in txt and '外圈0' not in txt:
            return f'{path}: source {msg_id} does not confirm stationary outer ring'
    elif path == 'bearing.application':
        if '高速电机' not in txt:
            return f'{path}: source {msg_id} lacks application context'
    elif path == 'engineering.lubrication.mode' and val == 'oil':
        if '油润滑' not in txt:
            return f'{path}: source {msg_id} does not explicitly choose oil lubrication'
    elif path == 'operating.axial_load_direction':
        if '从电机侧指向负载侧' not in txt:
            return f'{path}: source {msg_id} does not mention axial load direction'
    elif path == 'operating.rotation_direction':
        if '顺时针' not in txt:
            return f'{path}: source {msg_id} does not mention rotation direction'
    elif str(val) not in txt:
        return f'{path}: user source {msg_id} does not contain value {val!r}'
    return None


def offline_checks(case, dialogues, reviews, schema):
    errs=[]
    validate=Draft202012Validator(schema)
    dialogue_schema=schema['$defs']['dialogue']
    for problem in validate.iter_errors(case):
        errs.append('SCHEMA: '+problem.message+' at '+'.'.join(map(str,problem.absolute_path)))
    c_id=case['case_id'];brief=case['reference_brief']
    d=brief['dimensions']; vals={k:d[k]['value'] for k in ('d_mm','D_mm','B_mm')}
    if any(not isinstance(x,(int,float)) or isinstance(x,bool) for x in vals.values()):
        errs.append('DIMENSIONS: need numeric d/D/B')
    elif not (0 < vals['d_mm'] < vals['D_mm'] and vals['B_mm']>0):
        errs.append('DIMENSIONS: require 0<d<D and B>0')
    row=case['robas_catalog_evidence']['model']['matched_row']
    if str(row['model'])!=str(brief['bearing']['model']['value']) or any(vals[k]!=row[k] for k in vals):
        errs.append('CATALOG_MODEL: matched row inconsistent with selected model or d/D/B')
    for group,names in [('materials',[brief['engineering']['materials'][k] for k in ('inner_ring_id','outer_ring_id','ball_id')]+[brief['engineering']['cage']['material_id']]),
                        ('lubricants',[brief['engineering']['lubrication']['lubricant_id']])]:
        catalog=case['robas_catalog_evidence'][group]
        for v in names:
            key=v['value']
            snap=catalog.get(key)
            if not snap or snap['name']!=key or snap['raw_row'].get(snap.get('source_key_column'))!=key:
                errs.append(f'CATALOG_{group.upper()}: {key!r} not backed by own raw-row snapshot')
            match=v.get('catalog_match') or {}
            if not match or match.get('key_value')!=key or (snap and match.get('source_sha256')!=snap['source_sha256']):
                errs.append(f'CATALOG_{group.upper()}: {key!r} parameter evidence mismatch')
    for name,snap in case['robas_catalog_evidence']['lubricants'].items():
        props=snap['parsed_properties']
        for k in ['kinematic_viscosity_1','kinematic_viscosity_2']:
            if props[k]['value']<=0:
                errs.append(f'LUBRICANT: {name} has nonpositive {k}')
        if props['temperature_1']['value'] >= props['temperature_2']['value']:
            errs.append(f'LUBRICANT: {name} has unordered sample temperatures')
    ids=[x['dialogue_id'] for x in dialogues]
    if len(ids)!=len(set(ids)): errs.append('DIALOGUE: duplicate dialogue_id')
    if set(ids)!=set(case['dialogue_refs']): errs.append('DIALOGUE: dialogue_refs mismatch actual records')
    if any(x['case_id']!=c_id or x['simulated_user_profile']['case_id']!=c_id or
           x['expected_final_brief_case_id']!=c_id for x in dialogues):
        errs.append('DIALOGUE: case_id mismatch')
    for x in dialogues:
        for problem in Draft202012Validator(dialogue_schema).iter_errors(x):
            errs.append('DIALOGUE_SCHEMA: '+problem.message)
        turns=x['reference_turns']
        tids=[t['message_id'] for t in turns]
        if len(tids)!=len(set(tids)) or turns[0]['role']!='user' or x['initial_user_request']!=turns[0]['text']:
            errs.append(f'DIALOGUE: {x["dialogue_id"]} has duplicated turns or mismatched initial request')
        if turns[-1]['role']!='user' or '确认' not in turns[-1]['text']:
            errs.append(f'DIALOGUE: {x["dialogue_id"]} missing final explicit user acceptance')
        for i,t in enumerate(turns):
            if (i%2==0 and t['role']!='user') or (i%2==1 and t['role']!='assistant_reference'):
                errs.append(f'DIALOGUE: {x["dialogue_id"]} turn order invalid')
    if dialogues:
        primary=next((x for x in dialogues if x['dialogue_id'].endswith('-A')),None)
        if primary:
            user_msgs={t['message_id']:t['text'] for t in primary['reference_turns'] if t['role']=='user'}
            for path, value in find_params(brief):
                err=prove_user_source(path,value,user_msgs)
                if err:errs.append('PROVENANCE: '+err)
            for rule in brief['requirements']['constraints']:
                mid=rule.get('source_message_id')
                if mid not in user_msgs or str(rule.get('value')) not in user_msgs[mid]:
                    errs.append('PROVENANCE: constraint not in cited user turn')
        else:errs.append('PROVENANCE: missing canonical dialogue variant A')
    if case['initial_user_request']!=next((x['initial_user_request'] for x in dialogues if x['dialogue_id'].endswith('-A')),None):
        errs.append('PROVENANCE: design_cases.initial_user_request does not equal dialogue A initial request')
    if brief['delivery_state']['brief_complete'] and not case['validation']['engineering_reviewed']:
        errs.append('REVIEW: cannot mark complete when engineering config unreviewed')
    if (case['validation']['engineering_reviewed'] or case['validation']['robas_solver_verified'] or
       case['validation'].get('status') in ('ENGINEERING_REVIEWED','SOLVER_VERIFIED')):
        errs.append('REVIEW: this sample contains no professional approval or solver run evidence; cannot assert reviewed/verified')
    if brief['solver_context']['profile_ref'] is None and brief['delivery_state']['robas_template_ready']=='TEMPLATE_READY':
        errs.append('SOLVER: cannot claim TEMPLATE_READY without profile')
    record=reviews.get(c_id)
    if record is None:
        errs.append('REVIEW_CSV: missing case')
    else:
        if record['model']!=str(brief['bearing']['model']['value']): errs.append('REVIEW_CSV: wrong model')
        if record['brief_complete'].upper()!='NO' and not brief['delivery_state']['brief_complete']:
            errs.append('REVIEW_CSV: completion status mismatch')
    return errs


def online_checks(case, archive, source_archive=None):
    errs=[]
    if sha(archive.read_bytes())!=case['robas_catalog_evidence']['archive_sha256']:
        return ['SOURCE: RoBAS archive SHA256 mismatch (different resource version)']
    with zipfile.ZipFile(archive) as z:
        def check_file(path, expected):
            if path not in z.namelist():
                errs.append('SOURCE: missing '+path);return None
            b=z.read(path)
            if sha(b)!=expected:errs.append('SOURCE: SHA mismatch '+path)
            return b
        cat=case['robas_catalog_evidence']
        for field, path, key, propmap in [('materials',MAT,'materialName',MATERIAL_COLUMNS),('lubricants',LUB,'oilName',LUBRICANT_COLUMNS)]:
            snaps=cat[field]
            b=check_file(path,next(iter(snaps.values()))['source_sha256'])
            if b is None:continue
            rows=list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
            for name,snap in snaps.items():
                if snap['source_path']!=path or sha(b)!=snap['source_sha256']:
                    errs.append(f'SOURCE: {field} source identity mismatch for {name}')
                found=[(j+2,row) for j,row in enumerate(rows) if row.get(key)==name]
                if len(found)!=1:
                    errs.append(f'SOURCE: {name} missing/ambiguous in {path}');continue
                rownum,row=found[0]
                if snap['csv_line']!=rownum or snap['raw_row']!=row:
                    errs.append(f'SOURCE: {name} original CSV row differs')
                if snap['source_key_column']!=key:errs.append(f'SOURCE: {name} incorrect key field')
                for friendly,col in propmap.items():
                    try:expected=Decimal(row[col]);got=Decimal(str(snap['parsed_properties'][friendly]['value']))
                    except (KeyError,InvalidOperation) as e:
                        errs.append(f'SOURCE: {name} missing property {friendly}: {e}');continue
                    if abs(expected-got)>max(Decimal('1e-15'),abs(expected)*Decimal('1e-10')):
                        errs.append(f'SOURCE: {name} parsed {friendly} differs from CSV')
        model=cat['model']; dbb=check_file(model['source_path'],model['source_sha256'])
        if dbb:
            conn=sqlite3.connect(':memory:');conn.deserialize(dbb)
            try:rows=conn.execute('SELECT model,d,Dd,B,rsmin FROM model WHERE model=?',(model['matched_row']['model'],)).fetchall()
            finally:conn.close()
            if len(rows)!=1 or any(float(rows[0][i])!=float(model['matched_row'][k]) for i,k in [(1,'d_mm'),(2,'D_mm'),(3,'B_mm')]):
                errs.append('SOURCE: model row differs from actual SQLite')
    if source_archive:
        info=case['robas_catalog_evidence']['cage_implementation']
        with zipfile.ZipFile(source_archive) as z:
            path=info['source_path']
            if path not in z.namelist(): errs.append('SOURCE: cage C# path missing')
            else:
                b=z.read(path)
                if sha(b)!=info['source_sha256'] or 'new StampingCage()' not in b.decode('utf-8-sig',errors='replace'):
                    errs.append('SOURCE: cage source code mismatch')
    return errs


def load(dataset):
    schema=json.loads((dataset/'schema/DGBCase_v1.schema.json').read_text(encoding='utf-8'))
    cases=read_jsonl(dataset/'data/design_cases.jsonl')
    dialogues=read_jsonl(dataset/'data/dialogue_cases.jsonl')
    with (dataset/'review/case_review.csv').open(encoding='utf-8-sig',newline='') as f:
        reviewrows=list(csv.DictReader(f))
    review={r['case_id']:r for r in reviewrows}
    return schema,cases,dialogues,review


def self_test(case, dialogues, reviews, schema, archive):
    tests=[]
    def t(name,modify):
        sample=copy.deepcopy(case); ds=copy.deepcopy(dialogues)
        modify(sample,ds)
        errors=offline_checks(sample,ds,reviews,schema)
        if archive:errors+=online_checks(sample,archive)
        if not errors:raise AssertionError(f'negative test not caught: {name}')
        tests.append((name,errors[0]))
    t('fictitious material',lambda d,_:d['reference_brief']['engineering']['materials']['inner_ring_id'].update(value='虚构钢材'))
    t('negative oil viscosity',lambda d,_:d['robas_catalog_evidence']['lubricants']['VG32']['parsed_properties']['kinematic_viscosity_1'].update(value=-1))
    t('wrong model size',lambda d,_:d['robas_catalog_evidence']['model']['matched_row'].update(d_mm=90))
    t('outside smaller than bore',lambda d,_:d['reference_brief']['dimensions']['D_mm'].update(value=5))
    t('fake solver approval',lambda d,_:d['validation'].update(robas_solver_verified=True))
    t('null as confirmed',lambda d,_:d['reference_brief']['operating']['axial_load_n'].update(value=None,confirmed=True))
    t('unknown dialogue link',lambda d,_:d.update(dialogue_refs=['DIALOGUE-DGB-9999-Z']))
    t('wrong dimension source',lambda d,_:d['reference_brief']['dimensions']['d_mm']['source'].update(message_id='u01'))
    t('wrong material raw row',lambda d,_:d['robas_catalog_evidence']['materials']['氮共渗轴承钢']['raw_row'].update(materialName='另一种钢'))
    t('inconsistent review status',lambda d,_:d['reference_brief']['delivery_state'].update(brief_complete=True))
    print(f'PASS {len(tests)} negative checks: '+', '.join(x[0] for x in tests))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=Path(__file__).resolve().parents[1]/'DGB_Design_Dataset')
    parser.add_argument('--robas-archive',type=Path,help='Original RoBAS_Resources.zip for reproducible catalog check')
    parser.add_argument('--source-archive',type=Path,help='Optional original RoBAS C# source ZIP for StampingCage check')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    schema,cases,dialogues,reviews=load(args.dataset)
    if len(cases)!=len(set(c['case_id'] for c in cases)):
        raise SystemExit('FAIL: duplicate design case ID')
    if len(reviews)!=len(cases):raise SystemExit('FAIL: review count differs from design case count')
    all_errors=[]
    for case in cases:
        ds=[d for d in dialogues if d['case_id']==case['case_id']]
        err=offline_checks(case,ds,reviews,schema)
        if args.robas_archive:err+=online_checks(case,args.robas_archive,args.source_archive)
        all_errors.extend(f'{case["case_id"]}: {e}' for e in err)
    if all_errors:
        print('\n'.join('FAIL '+e for e in all_errors));raise SystemExit(1)
    if args.self_test:
        self_test(cases[0],[d for d in dialogues if d['case_id']==cases[0]['case_id']],reviews,schema,args.robas_archive)
    print(f'PASS: {len(cases)} design case(s), {len(dialogues)} dialogue variant(s), {len(reviews)} review row(s)')
    if args.robas_archive:print('PASS: independent RoBAS CSV/SQLite archive SHA, selected rows, parsed values and model dimensions match')
    else:print('LIMITED: schema/cross-file/provenance passed; RoBAS catalog NOT freshly verified (supply --robas-archive)')
    print('NOT CLAIMED: professional material/fit/clearance approval, solver feasibility, or manufacturing approval')


if __name__=='__main__':
    main()
