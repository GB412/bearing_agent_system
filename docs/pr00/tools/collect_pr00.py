"""Read-only local PR-00 evidence collector; no solver or product implementation."""
from pathlib import Path
import ast
import csv
import hashlib
import importlib.util
import json
import re
import sqlite3
import sys
from collections import Counter

ROOT = Path('D:/RotorStudio/bearing_agent_system')
SRC = Path('D:/RotorStudio/RoBAS')
CAD = Path('D:/RotorStudio/Bearing_CAD/Bearing_CAD')
RES = Path('D:/RotorStudio/ui_rotorstudio-9857bcc7afce658be15dfd2b559a55cb12b55bbd/NetLib/RoBAS_Resources')
CASE = CAD / 'build/robas-solver01-acceptance-20261108/real-DGB/run-85ffea6353a545bc822c50a2b3ced583/DATA.txt'
OUT = ROOT / 'docs/pr00/evidence'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def balanced(text, start):
    pos = text.index('{', start)
    level = 1
    end = pos + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[pos:end]

def location(p, text, offset):
    return f'{p.relative_to(SRC).as_posix()}:{text.count(chr(10), 0, offset)+1}'

def properties(p):
    text = p.read_text(encoding='utf-8-sig')
    result = {}
    for m in re.finditer(r'public\s+(?:static\s+)?(?:double|int|Decimal|string|int\[\]|eAnalysisType)\s+(\w+)\s*\{', text):
        block = balanced(text, m.start())
        prefix = text[max(0, m.start()-400):m.start()]
        result[m[1].lower()] = {'name':m[1], 'ref':location(p,text,m.start()), 'body':block,
                                      'attribute_context':prefix[prefix.rfind('} ')+2:]}
    return result

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('audit_robas_data', CAD/'bearing_cad/robas_data.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    ball = ast.parse((CAD/'bearing_cad/robas_ball_input.py').read_text(encoding='utf-8'))
    extra = ast.literal_eval(next(n.value.left.right for n in ball.body if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_RECORD_FIELDS' for t in n.targets)))
    layout = mod.COMMON_HEAD + extra + mod.COMMON_TAIL
    rows = list(csv.reader(CASE.read_text(encoding='utf-8-sig').splitlines()))
    analysis = SRC/'Core/BallBearing/BallBearingAnalysis.cs'
    at = analysis.read_text(encoding='utf-8-sig')
    static = balanced(at,at.index('private string[] generateStaticAnalysisInputs'))
    serial = re.findall(r'''string.Format\("'(rec [^']+)'[^"]*",\s*([^\n]+)''', static)
    assert len(serial)==len(layout)==len(rows)==43
    classpaths = {'Solver':['Core/BaseSolver.cs'], 'Geometry':['Core/BallBearing/BallBearingGeometry.cs','Core/BaseGeometry.cs'], 'BC':['Core/BaseBC.cs'], 'Material':['Core/Material/Material.cs'], 'Lubricant':['Core/Lubricant/Lubricant.cs']}
    cache = {k:[(SRC/p,(SRC/p).read_text(encoding='utf-8-sig'),properties(SRC/p)) for p in paths] for k,paths in classpaths.items()}
    dgbp = SRC/'Core/BallBearing/DeepGroveBallBearing/DeepGrooveBallBearing.cs'
    dgb = dgbp.read_text(encoding='utf-8-sig')
    setblock = balanced(dgb,dgb.index('public override void SetAnalysisValue'))
    cadtext = (CAD/'bearing_cad/robas_ball_input.py').read_text(encoding='utf-8')
    csvmap = {'elasticModules': 'elsaModules(Pa)', 'density':'density(kg/m3)', 'conductivity':'heatConductivity(w/m/k)', 'thermalExpansion':'linearExpan(1/k)', 'poissonRatio':'poisson', 'specificHeat':'specificHeat'}
    fields = []
    source_corpus = [(p,p.read_text(encoding='utf-8-sig')) for p in sorted(SRC.rglob('*.cs'))]
    for i, ((label,names),(sl,expr),case) in enumerate(zip(layout,serial,rows)):
        assert label==sl==case[0].strip("'") and len(case)==len(names)+1
        owner = 'Solver' if i<=8 else 'Geometry' if i<=14 else 'Material' if i<=27 else 'BC' if i<=35 or i==42 else 'Lubricant'
        object_name = re.search(r'(Solver|Geometry|\w*Material|BC|Lubricant)\.',expr)[1]
        for col,name in enumerate(names,1):
            key = re.sub(r'(?<=kStaticConstraint)\d$|(?<=kPltElemInd)\d$|(?<=iCageGuide)\d$','',name)
            prop = next((props[key.lower()] for p,t,props in cache[owner] if key.lower() in props),None)
            defaults=[]
            for p,t,props in cache[owner]:
                cname=p.stem
                cm=re.search(r'public '+cname+r'\(\)',t)
                if cm:
                    cb=balanced(t,cm.start())
                    for m in re.finditer(r'\b'+key+r'\s*=\s*([^;]+);',cb):
                        offset=t.index(cb)+m.start()
                        defaults.append({'ref':location(p,t,offset),'expression':m[1]})
            assignment=[]
            pn=prop['name'] if prop else name[0].upper()+name[1:]
            for m in re.finditer(r'Analysis\.(?:Geometry|Solver)\.'+re.escape(pn)+r'\s*=\s*([^;]+);',setblock):
                assignment.append({'ref':location(dgbp,dgb,dgb.index(setblock)+m.start()),'expression':m[1]})
            optimization=(i==5 and name=='nRe') or (i==10 and name in ('bReDia','pitchDia','raceCurFac1','raceCurFac2'))
            category='REFERENCE_PROFILE_UNVERIFIED'
            if owner=='Solver': category='SOLVER_PROFILE'
            if owner=='Material' and name in csvmap: category='ROBAS_DATABASE'
            if assignment: category='DERIVED'
            if i==9 and name in ('brgBore','brgOD','raceWidth1','raceWidth2'): category='USER_INPUT'
            if i in (28,29,30,31,42): category='USER_INPUT'
            if i==10 and name in ('freeIntCls','shoulderDia1','shoulderDia2','shimThickness1','shimThickness2','rmsAspHt1','rmsAspHt2'): category='USER_INPUT'
            if optimization: category='OPTIMIZATION_VARIABLE'
            attrs = prop['attribute_context'] if prop else ''
            unit='BLOCKED: 原版无明确单位注释/需协议手册'
            if owner=='Geometry' and name not in ('raceCurFac1','raceCurFac2','freeConAngDeg','cageAngCut','cageConeAng') and (i==9 or i==10 or i in (12,13,14)): unit='m（属性 mm ↔ backing /1000）'
            if i in (3,4): unit='text'
            if owner=='Solver' and i!=1: unit='编码/整数或 text；详细语义需配置审核'
            if name in ('raceCurFac1','raceCurFac2'):unit='1（沟半径/Dw，Python；原版自动属性断链）'
            if name=='freeConAngDeg':unit='deg'
            units={'density':'kg/m³','elasticModules':'Pa','poissonRatio':'1','thermalExpansion':'1/K','specificHeat':'J/kg/K','conductivity':'W/m/K','appLoadX':'N','appLoadY':'N','appLoadZ':'N','appMomY':'N·m','appMomZ':'N·m','rpm1':'rpm','rpm2':'rpm'}
            unit=units.get(name,unit)
            if i==31 or name in ('roomTemp','baseTemp'):unit='K（UI ℃；MathMethod 换算实现 BLOCKED）'
            if name.startswith('gravityVec'):unit='m/s²'
            if name.startswith('appDisp') or name in ('raceFit1','raceFit2'):unit='m'
            pyhits=[f'robas_ball_input.py:{n}: {line.strip()}' for n,line in enumerate(cadtext.splitlines(),1) if f'"{name}"' in line]
            seroffset=at.index(expr.strip(),at.index('private string[] generateStaticAnalysisInputs'))
            fields.append({'record':i+1,'label':label,'column':col,'field':name,'owner':object_name,'category':category,'unit':unit,'serialize_ref':location(analysis,at,seroffset),'default':defaults,'property':prop,'set_analysis':assignment,'database':('Resource/materialDB.csv[materialName].'+csvmap[name]+'; MaterialServer.GetMaterialByNameFromDataTable' if owner=='Material' and name in csvmap else '无已证实 DATA 数据库直连'),'python':pyhits,'case_value':case[col].strip("'"),'status':('OPT_PENDING' if optimization and name not in ('raceCurFac1','raceCurFac2') else 'BLOCKED'),'confirmation':('后续优化器供值，非用户确认' if optimization else '用户确认数值/选择，或工程审核受信规则/profile；案例值不等于确认')})
    for f in fields:
        key = re.sub(r'(?<=kStaticConstraint)\d$|(?<=kPltElemInd)\d$|(?<=iCageGuide)\d$','',f['field'])
        f['source_references'] = [location(p,t,m.start()) for p,t in source_corpus for m in re.finditer(r'\b'+re.escape(key)+r'\b',t,re.I)]
    inventory=[]
    for base in (SRC,):
        inventory += [{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(base.rglob('*.cs'))]
    resources = list((RES/'Data').glob('*.db'))+list((RES/'Resource').glob('*DB*.csv'))+[RES/'exe/RoBAS_v2.exe',CASE,CAD/'bearing_cad/robas_data.py',CAD/'bearing_cad/robas_ball_input.py',CAD/'bearing_cad/robas_analysis.py',Path('C:/RollBearing/RollBearing.exe'),Path('C:/RollBearing/exe/DATA.txt')]
    resources += list(Path('C:/RollBearing/Data').glob('*.db'))+list(Path('C:/RollBearing/Resource').glob('*DB*.csv'))
    inventory += [{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in resources if p.exists()]
    databases=[]
    for p in sorted((RES/'Data').glob('*.db')):
        con=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True)
        tables=[]
        for name,sql in con.execute("select name,sql from sqlite_master where type='table' order by name"):
            q='"'+name.replace('"','""')+'"'
            tables.append({'name':name,'ddl':sql,'columns':list(con.execute('pragma table_info('+q+')')),'rows':con.execute('select count(*) from '+q).fetchone()[0]})
        con.close()
        databases.append({'path':str(p),'sha256':sha(p),'tables':tables})
    csvs=[]
    for p in (RES/'Resource').glob('*DB*.csv'):
        raw=p.read_bytes()
        try: text=raw.decode('utf-8-sig'); encoding='utf-8-sig'
        except UnicodeDecodeError:text=raw.decode('gb18030');encoding='gb18030'
        rr=list(csv.reader(text.splitlines()))
        csvs.append({'path':str(p),'encoding':encoding,'sha256':sha(p),'header':rr[0],'rows':len(rr)-1,'sample':rr[1:3]})
    evidence={'schema':1,'baseline':'02861ea09e77906f4360ed1e3e9c7268a0c9ea1f','bearing_cad_commit':'4460a784846d7df978579f49e8685a18da336e81','case_path':str(CASE),'case_sha256':sha(CASE),'record_count':len(layout),'field_count':len(fields),'counts':dict(Counter(f['category'] for f in fields)),'fields':fields,'inventory':inventory,'databases':databases,'csv':csvs}
    (OUT/'audit.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def cell(s):return str(s).replace('|','\\|').replace('\n',' ')
    md=['# DGB RoBAS 拟静力学逐字段审计矩阵','', '2026-11-20；43 条记录；'+str(len(fields))+' 个标量/文本字段（不含标签）。状态：源码定位完成，工程输入冻结 BLOCKED。', '', '证据源根目录 `D:/RotorStudio/RoBAS/`；Python 根目录 `D:/RotorStudio/Bearing_CAD/Bearing_CAD/bearing_cad/`。', '', '所有字段的 getter/setter 完整片段、属性上下文、默认表达式/行号、赋值/依赖、Python 行号和实际案例值均保存在 [audit.json](../pr00/evidence/audit.json)。本表默认值仅证明初始化，不证明工程适用性。', '', '类别统计：`'+json.dumps(evidence['counts'],ensure_ascii=False)+'`。ROBAS_DATABASE 在本次特指原版 CSV，非 SQLite。分类表示预期主来源，BLOCKED 表示单位、适用性、确认链至少一项未关闭。OPT_PENDING 同样阻断可运行 DATA。', '', '原版 `BallBearingAnalysis.generateStaticAnalysisInputs()` 直接写 backing fields；数组已展开，重复 rec 7.2.x 以物理记录序号区分。除五变量外，依赖其值的派生字段也必须保持待计算，不能继承案例。','']
    for i,(label,names) in enumerate(layout,1):
        md += [f'## {i}. {label}', '', '|列|字段 / 对象|单位|主来源|C# 序列化；属性 / 默认 / 赋值依赖|数据库 / Python|案例值|确认 / 状态|','|---:|---|---|---|---|---|---|---|']
        for f in [f for f in fields if f['record']==i]:
            prop=f['property']
            refs=f["serialize_ref"]+'；'+(prop['ref']+' '+prop['name'] if prop else '无 getter/setter：直接 public field')+'；默认 '+ '; '.join(x['ref']+' = '+x['expression'] for x in f['default'])+'；SetAnalysisValue '+('; '.join(x['ref']+' = '+x['expression'] for x in f['set_analysis']) or '未赋此字段')
            py='; '.join(f['python']) or ('robas_analysis.py: _MATERIAL_VALUES（6项）' if f['category']=='ROBAS_DATABASE' else '参考 profile 保留；底层显式 override 能力见报告')
            md.append('|'+ '|'.join(cell(v) for v in [f['column'],f['field']+' / '+f['owner'],f['unit'],f['category'],refs,f['database']+'；'+py,f['case_value'],f['confirmation']+'；'+f['status']])+'|')
        md.append('')
    (ROOT/'docs/parameter_catalog/DGB_ROBAS_QUASI_STATIC_INPUT_MATRIX.md').write_text('\n'.join(md).rstrip()+'\n',encoding='utf-8')
    print(json.dumps({k:evidence[k] for k in ('record_count','field_count','counts','case_sha256')},ensure_ascii=False))

if __name__=='__main__':main()
