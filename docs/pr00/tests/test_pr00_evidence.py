"""Audit artifact checks only; these do not implement an engineering validator."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
E = json.loads((ROOT/'docs/pr00/evidence/audit.json').read_text(encoding='utf-8'))
F = E['fields']

def test_complete_unique_field_identity_and_counts():
    assert E['record_count']==43
    assert E['field_count']==len(F)==324
    assert len({(f['record'],f['column']) for f in F})==324
    assert dict(Counter(f['category'] for f in F))==E['counts']
    assert len({f['record'] for f in F})==43
    for n in range(1,44):
        cols=[f['column'] for f in F if f['record']==n]
        assert cols==list(range(1,len(cols)+1))

def test_five_optimization_slots_do_not_claim_validated_input():
    opt=[f for f in F if f['category']=='OPTIMIZATION_VARIABLE']
    assert {(f['record'],f['column'],f['field']) for f in opt}=={
        (6,3,'nRe'),(11,1,'bReDia'),(11,2,'pitchDia'),(11,5,'raceCurFac1'),(11,6,'raceCurFac2')}
    assert all(f['status'] in ('OPT_PENDING','BLOCKED') for f in opt)
    for f in opt:
        if f['field'].startswith('raceCurFac'):
            assert not f['set_analysis']
            assert 'get; set;' in f['property']['body']

def test_every_field_has_source_default_case_and_explicit_confirmation():
    for f in F:
        assert f['default'] and f['serialize_ref'] and f['source_references']
        assert f['case_value']!=''
        assert f['confirmation'] and f['status'] in ('OPT_PENDING','BLOCKED')
        assert f['category']!='DEFAULT'

def test_csv_only_covers_six_material_properties():
    db=[f for f in F if f['category']=='ROBAS_DATABASE']
    assert len(db)==34
    assert all('materialDB.csv' in f['database'] for f in db)
    assert not any(f['record']>=22 for f in db)
    lub=[c for c in E['csv'] if Path(c['path']).name=='lubricantDB.csv'][0]
    assert lub['rows']==31
    assert lub['header'][0]=='oilName'
    assert 'pocVis' not in lub['header']

def test_shim_property_does_not_write_serialized_field():
    f=next(f for f in F if f['record']==11 and f['field']=='shimThickness1')
    assert 'freeIntCls = value / 1000' in f['property']['body']
    assert 'shimThickness1 = value' not in f['property']['body']

def test_sqlite_ddl_and_counts_have_actual_evidence():
    assert len(E['databases'])==7
    d=next(d for d in E['databases'] if Path(d['path']).name=='DGBData.db')
    model=next(t for t in d['tables'] if t['name']=='model')
    assert model['rows']==145
    assert [c[1] for c in model['columns']]==['model','d','Dd','B','rsmin']
    assert model['columns'][0][5]==1
    assert all(t['ddl'] and t['columns'] and t['rows']>=0 for d in E['databases'] for t in d['tables'])

def test_matrix_contains_all_fields_in_record_sections():
    text=(ROOT/'docs/parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md').read_text(encoding='utf-8')
    sections=re.split(r'^## \d+\. ',text,flags=re.M)[1:]
    assert len(sections)==43
    for n,section in enumerate(sections,1):
        rows=[line for line in section.splitlines() if re.match(r'^\|\d+\|',line)]
        assert len(rows)==len([f for f in F if f['record']==n])
        for f in [f for f in F if f['record']==n]:
            assert f'|{f["column"]}|{f["field"]} / ' in section

def test_document_links_resolve():
    for p in [ROOT/'README.md',*(ROOT/'docs').rglob('*.md')]:
        text=p.read_text(encoding='utf-8')
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in link or link.startswith('#'):
                continue
            assert (p.parent/link.split('#')[0]).exists(),(str(p),link)

def test_engineering_gate_and_blockers_remain_explicit():
    text=(ROOT/'docs/pr00/PR-00_ROBAS_QUASI_STATIC_INPUT_AUDIT.md').read_text(encoding='utf-8')
    for token in ['TEMPLATE_READY','RUNNABLE_READY','INCOMPLETE','confirmed/unconfirmed',
                  '禁止序列化','B01','B10','未运行','DLAP','StateManager']:
        assert token in text

def require_local():
    p=Path(E['case_path'])
    if not p.is_file():pytest.skip('Local proprietary sources/case are not distributed')
    return p

def test_local_resources_unchanged_since_audit():
    require_local()
    for item in E['inventory']:
        p=Path(item['path'])
        assert p.is_file(),str(p)
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],str(p)

def test_local_serialization_position_is_backing_field_not_property():
    require_local()
    p=Path('D:/RotorStudio/RoBAS/Core/BallBearing/BallBearingAnalysis.cs')
    lines=p.read_text(encoding='utf-8-sig').splitlines()
    for f in F:
        line=int(f['serialize_ref'].rsplit(':',1)[1])
        key=re.sub(r'(?<=kStaticConstraint)\d$|(?<=kPltElemInd)\d$|(?<=iCageGuide)\d$','',f['field'])
        assert f'{f["owner"]}.{key}' in lines[line-1]

def test_local_golden_roundtrip_compares_every_numeric_and_text_token():
    p=require_local()
    cad=Path('D:/RotorStudio/Bearing_CAD/Bearing_CAD')
    sys.path.insert(0,str(cad))
    from bearing_cad.robas_ball_input import BallDataDocument,update_ball_data
    assert hashlib.sha256(p.read_bytes()).hexdigest()==E['case_sha256']
    doc=BallDataDocument.read(p)
    updated=update_ball_data(p,None,geometry_mode='legacy_data',operating_updates={})
    rendered=updated.render()
    assert rendered.count('\r\n')==43
    assert BallDataDocument.parse(rendered).rows==doc.rows
    for f in F:
        assert doc.value(f['record']-1,f['field']).strip("'")==f['case_value']
    assert p.read_bytes().count(b'\r\n')==43
