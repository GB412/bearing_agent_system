"""Generate synthetic DGB design tasks from *actual* locally provided RoBAS catalogs.

The scenarios and performance targets are synthetic user requirements, not engineering
approval, validated physical feasibility, or measured solver results.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DGB_Design_Dataset"
VARIABLES = ["Dw_mm", "Z", "Dpw_mm", "fi", "fo"]
MAT_PATH = "RoBAS_Resources/Resource/materialDB.csv"
LUB_PATH = "RoBAS_Resources/Resource/lubricantDB.csv"
MODEL_PATH = "RoBAS_Resources/Data/DGBData.db"
RING_MATERIALS = {"氮共渗轴承钢", "渗碳轴承钢"}
CAGE_MATERIAL = "工具钢"
LUBRICANTS = {"VG22", "VG32", "VG46", "VG68", "VG100"}

# Distinct user requirements: applications, dimensions, operating conditions, targets,
# and different optimization locks / bounds. None is claimed physically feasible.
def spec(model, app, ni, no, fr, fa, temp, ring, lub, clr, fit, obj, cons, opt="all"):
    return dict(model=model, app=app, ni=ni, no=no, fr=fr, fa=fa, temp=temp,
                ring=ring, lub=lub, clr=clr, fit=fit, obj=obj, cons=cons, opt=opt)

CASES = [
 spec("6205","高速电机转子支承",15000,0,300,50,60,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("L10h",">=",20000,"h")]),
 spec("6003","小型鼓风机轴承",14000,0,180,0,55,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",12000,"h")]),
 spec("6004","电动通风机电机支承",18000,0,240,30,65,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_temperature_rise",[("power_loss_w","<=",5,"W"),("L10h",">=",15000,"h")]),
 spec("6005","循环冷却风机",12500,0,500,0,70,"渗碳轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("L10h",">=",15000,"h")]),
 spec("6006","高速电主轴辅助支承",20000,0,450,80,75,"氮共渗轴承钢","VG22","C3","k5/H7","maximize_radial_stiffness",[("L10h",">=",15000,"h")]),
 spec("6007","离心泵电机支承",9000,0,1000,200,80,"渗碳轴承钢","VG46","C3","m5/H7","maximize_L10h",[("L10h",">=",25000,"h")]),
 spec("6008","数控驱动电机支承",11000,0,900,100,70,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",25,"degC")]),
 spec("6203","轴流风机电机",16000,0,320,40,58,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",18000,"h")],"lockZ"),
 spec("6204","小型工业减速器",6000,0,1500,150,78,"渗碳轴承钢","VG46","CN","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",2000,"MPa")],"boundDw"),
 spec("6205","循环泵传动端轴承",9000,0,1100,120,72,"氮共渗轴承钢","VG32","C3","k5/H7","maximize_L10h",[("L10h",">=",30000,"h")],"lockZ"),
 spec("6206","输送装置滚筒支承",3000,0,2700,100,68,"渗碳轴承钢","VG68","CN","m5/H7","maximize_L10h",[("L10h",">=",25000,"h")],"boundDw"),
 spec("6207","工厂齿轮箱径向支承",4500,0,3300,230,75,"氮共渗轴承钢","VG68","C3","m5/H7","minimize_peak_contact_pressure",[("L10h",">=",25000,"h")],"lockZ"),
 spec("6208","机油输送泵支承",5500,0,3000,0,83,"渗碳轴承钢","VG46","CN","k5/H7","minimize_power_loss",[("power_loss_w","<=",25,"W")],"boundDw"),
 spec("6304","中小型机械旋转关节",2500,0,2200,300,50,"氮共渗轴承钢","VG32","CN","k5/H7","maximize_radial_stiffness",[("L10h",">=",40000,"h")]),
 spec("6305","农机传动轴支承",1800,0,4200,150,65,"渗碳轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",30000,"h")]),
 spec("6306","工艺空气压缩机辅助支承",7500,0,3000,250,87,"氮共渗轴承钢","VG46","C3","k5/H7","minimize_power_loss",[("temperature_rise_c","<=",25,"degC")]),
 spec("6307","液压电机轴承",3700,0,6500,500,92,"渗碳轴承钢","VG100","C3","m5/H7","minimize_peak_contact_pressure",[("L10h",">=",30000,"h")]),
 spec("6002","小型精密仪表旋转机构",9000,0,80,0,42,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",10000,"h")],"boundCurvature"),
 spec("6001","微型高速散热风扇",25000,0,60,10,53,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",10000,"h")]),
 spec("6209","制冷压缩机辅助轴承",3500,0,5500,450,88,"渗碳轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",35000,"h")],"lockZ"),
 spec("6210","通用重载传动轴支承",2200,0,7800,0,90,"渗碳轴承钢","VG100","C3","m5/H7","minimize_power_loss",[("temperature_rise_c","<=",30,"degC")],"boundDw"),
 spec("6308","工业搅拌机主轴支承",1500,0,12000,900,90,"氮共渗轴承钢","VG100","C3","m5/H7","maximize_L10h",[("L10h",">=",40000,"h")]),
 spec("6202","轻型传送设备端部轴承",3000,0,700,0,48,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",15,"degC")],"lockZ"),
 spec("6000","微型直流电机支承",21000,0,120,15,55,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",10000,"h")]),
]

OBJECTIVES = {
 "minimize_power_loss":"尽可能降低摩擦功耗",
 "maximize_L10h":"在满足其他要求时尽可能提高额定寿命",
 "minimize_temperature_rise":"尽可能减小轴承温升",
 "minimize_peak_contact_pressure":"尽可能降低滚动接触的峰值压力",
 "maximize_radial_stiffness":"尽可能提高径向支承刚度",
}
CONSTRAINTS = {
 "L10h":lambda n,u:f"额定寿命L10h不低于{n:g}小时",
 "power_loss_w":lambda n,u:f"摩擦功耗希望不超过{n:g} W",
 "temperature_rise_c":lambda n,u:f"温升希望不超过{n:g}℃",
 "peak_contact_pressure_mpa":lambda n,u:f"峰值接触压力希望不超过{n:g} MPa",
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def catalog_row(reader, col, key):
    matches = [(line, row) for line,row in reader if row[col] == key]
    if len(matches)!=1:
        raise ValueError(f"catalog key {col}={key!r} has {len(matches)} matches")
    return matches[0]

def assemble_request(c, idx):
    b,op,en,r,opt = c["bearing"],c["operating"],c["engineering"],c["requirements"],c["optimization"]
    d=c["dimensions"]
    openers=[
        f"我想为{b['application']}设计一套单列深沟球轴承。",
        f"需要一款用于{b['application']}的深沟球轴承，请按下面条件建立设计任务。",
        f"我这边的场景是{b['application']}，希望采用单列深沟球轴承。",
        f"请帮我做{b['application']}的轴承内部结构设计，轴承形式选深沟球。",
    ]
    dims=f"参考RoBAS型号{b['reference_model']}，只固定外形：内径{d['d_mm']:g} mm、外径{d['D_mm']:g} mm、宽度{d['B_mm']:g} mm，内部滚动体及沟道参数可重新设计。"
    speed=(f"内圈按{op['inner_speed_rpm']:g} rpm、外圈固定不转" if op['outer_speed_rpm']==0 else f"内圈{op['inner_speed_rpm']:g} rpm、外圈{op['outer_speed_rpm']:g} rpm")
    fa=(f"轴向载荷明确为0 N（没有轴向载荷）" if op['axial_load_n']==0 else f"轴向载荷{op['axial_load_n']:g} N、方向{op['axial_load_direction']}")
    working=f"运行条件为{speed}；单个轴承径向载荷{op['radial_load_n']:g} N，方向{op['radial_load_direction']}；{fa}；假定轴承分析工作温度{op['temperature_c']:g}℃。{op['rotation_direction']}。"
    materials=(f"材料按RoBAS材料目录中的“{en['inner_ring_material']}”选内圈和外圈，钢球也采用“{en['ball_material']}”；"
               f"保持架型式为{en['cage_type']}，保持架材料选目录里的“{en['cage_material']}”。"
               f"润滑方式为油润滑，润滑剂选RoBAS目录中的“{en['lubricant']}”。")
    install=f"初始径向游隙组别选{en['clearance_group']}，具体毫米值暂不指定；轴与内圈的配合代号为{en['shaft_fit']}，座孔与外圈的配合代号为{en['housing_fit']}。"
    constraints="，".join(CONSTRAINTS[e['metric']](e['value'],e['unit']) for e in r['constraints'])
    goal=f"我的性能要求是{constraints}；主要设计目标是{OBJECTIVES[r['objective']]}。这些是设计目标和约束，是否可满足、是否能由RoBAS现有模型计算，还要后续检查。"
    if opt['locked']:
        l=next(iter(opt['locked'].items()))
        o=f"五个内部参数中，{l[0]}按参考记录锁定为{l[1]:g}，其余{len(opt['variables'])}个交给优化模块调整。"
    elif opt['bounds']:
        v=next(iter(opt['bounds']))
        bound=opt['bounds'][v]
        o=(f"钢球直径Dw限定在{bound['min']:g}到{bound['max']:g} mm，其余内部参数由优化模块调整。"
           if v=="Dw_mm" else f"内圈沟曲率系数fi限定在{bound['min']:g}到{bound['max']:g}，其他内部参数由优化模块调整。")
    else:
        o="钢球直径Dw、球数Z、节圆直径Dpw、内沟曲率系数fi、外沟曲率系数fo均交给下一阶段优化，不提前固定。"
    closing="上述材料、保持架、润滑、游隙和配合是用户选定的候选配置，仅保证所用型号、材料和润滑名称在指定RoBAS资源中有记录，不代表组合已经过工程审核。"
    if idx % 3 == 0:
        return " ".join([openers[idx%4],dims,working,goal,materials,install,o,closing])
    if idx % 3 == 1:
        return " ".join([openers[idx%4],dims,materials,install,working,goal,o,closing])
    return " ".join([openers[idx%4],working,dims,goal,materials,install,o,closing])


def generate(archive: Path) -> tuple[int,int]:
    with zipfile.ZipFile(archive) as z:
        matb,lubb,dbb=(z.read(path) for path in (MAT_PATH,LUB_PATH,MODEL_PATH))
    mats=list(enumerate(csv.DictReader(io.StringIO(matb.decode("utf-8-sig"))),start=2))
    lubs=list(enumerate(csv.DictReader(io.StringIO(lubb.decode("utf-8-sig"))),start=2))
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        tmp.write(dbb); tmp.flush()
        con=sqlite3.connect(tmp.name)
        con.row_factory=sqlite3.Row
        models={s['model']:dict(con.execute('select model,d,Dd,B,rsmin from model where model=?',(s['model'],)).fetchone())
                for s in CASES}
        base_ref={s['model']:con.execute('select Dw,Z,Dwp from "主参数" where model=?',(s['model'],)).fetchone() for s in CASES}
        con.close()
    mat_ids=set().union(*(set([s['ring'],CAGE_MATERIAL]) for s in CASES))
    lub_ids={s['lub'] for s in CASES}
    if not mat_ids<=RING_MATERIALS|{CAGE_MATERIAL} or not lub_ids<=LUBRICANTS:
        raise ValueError("unknown material/lubricant")
    mats_dict={}
    for name in mat_ids:
        line,row=catalog_row(mats,'materialName',name)
        mats_dict[name]={
          'elastic_modulus_pa':float(row['elsaModules(Pa)']),
          'density_kg_m3':float(row['density(kg/m3)']),
          'thermal_conductivity_w_m_k':float(row['heatConductivity(w/m/k)']),
          'thermal_expansion_1_k':float(row['linearExpan(1/k)']),
          'poisson_ratio':float(row['poisson']),
          'specific_heat_j_kg_k':float(row['specificHeat']),
          'csv_line':line
        }
    lub_dict={}
    for name in lub_ids:
        line,row=catalog_row(lubs,'oilName',name)
        lub_dict[name]={
          'density0_source_value':float(row['density0']),
          'temperature_1_c':float(row['t1(degC)']),
          'kinematic_viscosity_1_m2_s':float(row['v1(m^2/s)']),
          'temperature_2_c':float(row['t2(degC)']),
          'kinematic_viscosity_2_m2_s':float(row['v2(m^2/s)']),
          'density_slope_source_value':float(row['slopeDensity']),
          'specific_heat0_j_kg_c':float(row['specificHeat0(J/kg/degC)']),
          'specific_heat_slope_source_value':float(row['slopeCp']),
          'csv_line':line
        }
    source={
       'resource_archive_sha256':sha(archive.read_bytes()),
       'model':{'file':MODEL_PATH,'sha256':sha(dbb),'table':'model','key_column':'model'},
       'materials':{'file':MAT_PATH,'sha256':sha(matb),'key_column':'materialName'},
       'lubricants':{'file':LUB_PATH,'sha256':sha(lubb),'key_column':'oilName'},
    }
    design=[]; requests=[]; review=[]
    for idx,s in enumerate(CASES,1):
        mid=s['model']; m=models[mid]
        if not m or tuple(m.keys()) != ('model','d','Dd','B','rsmin'):
            raise ValueError(f"bad model record {mid}")
        if s['fr']<0 or s['fa']<0 or s['ni']<0 or s['no']<0 or s['ni']==s['no']:
            raise ValueError("invalid operating tuple")
        dim={'d_mm':m['d'],'D_mm':m['Dd'],'B_mm':m['B']}
        o={'variables':VARIABLES.copy(),'locked':{},'bounds':{}}
        ref=base_ref[mid]
        if s['opt']=='lockZ':
            if ref is None:raise ValueError(f'No verified Z for {mid}')
            o['locked']['Z']=int(ref['Z']);o['variables'].remove('Z')
        elif s['opt']=='boundDw':
            if ref is None:raise ValueError(f'No verified Dw for {mid}')
            dw=float(ref['Dw'])
            o['bounds']['Dw_mm']={'min':round(dw*0.90,3),'max':round(dw*1.10,3)}
        elif s['opt']=='boundCurvature':
            o['bounds']['fi']={'min':0.51,'max':0.54}
        elif s['opt']!='all':raise ValueError('Unknown opt mode')
        fa_dir=('不适用（用户明确没有轴向载荷）' if s['fa']==0 else '沿轴线从电机侧指向负载侧')
        op={
         'inner_speed_rpm':s['ni'],'outer_speed_rpm':s['no'],
         'radial_load_n':s['fr'],'axial_load_n':s['fa'],'temperature_c':s['temp'],
         'rotation_direction':'从电机侧观察内圈顺时针旋转，外圈固定',
         'radial_load_direction':'竖直向下','axial_load_direction':fa_dir
        }
        ring=s['ring'];en={
          'inner_ring_material':ring,'outer_ring_material':ring,'ball_material':ring,
          'cage_type':'StampingCage','cage_material':CAGE_MATERIAL,
          'lubrication_mode':'oil','lubricant':s['lub'],
          'clearance_group':s['clr'],'initial_radial_clearance_mm':None,
          'shaft_fit':s['fit'].split('/')[0],'housing_fit':s['fit'].split('/')[1]
        }
        cons=[{'metric':metric,'operator':operator,'value':val,'unit':unit} for metric,operator,val,unit in s['cons']]
        record={
          'record_type':'design_case','case_id':f'DGB-{idx:04d}',
          'bearing':{'type':'DGB','application':s['app'],'reference_model':mid},
          'dimensions':dim,'operating':op,'engineering':en,
          'requirements':{'constraints':cons,'objective':s['obj'],'fixed_envelope':True},
          'optimization':o,
          'robas_data':{
             'model_record':{'model':mid,**dim,'rsmin_mm':m['rsmin']},
             'materials':{k:mats_dict[k] for k in sorted({ring,CAGE_MATERIAL})},
             'lubricants':{s['lub']:lub_dict[s['lub']]},'sources':{
                 **source,'model':{**source['model'],'key':mid}
             }
          },
          'quality':{
            'scenario_origin':'synthetic','catalog_verified':True,
            'engineering_reviewed':False,'solver_verified':False,
            'note':'原始RoBAS型号、材料、润滑记录已核实；具体配置适用性、速度极限、游隙/配合及约束可评估性均未工程审核。'
          }
        }
        request={'record_type':'user_request','request_id':f'REQ-{idx:04d}',
                 'case_id':record['case_id'],'text':assemble_request(record,idx)}
        design.append(record);requests.append(request)
        review.append({
          'case_id':record['case_id'],'application':s['app'],'reference_model':mid,
          'd_mm':m['d'],'D_mm':m['Dd'],'B_mm':m['B'],
          'inner_speed_rpm':s['ni'],'outer_speed_rpm':s['no'],
          'Fr_N':s['fr'],'Fa_N':s['fa'],'temperature_c':s['temp'],
          'objective':s['obj'],'optimization_mode':s['opt'],
          'catalog_verified':'YES','engineering_reviewed':'NO','solver_verified':'NO',
          'review_notes':'固定设计条件与性能目标为合成测试情境；RoBAS目录匹配不等于性能、材料组合或计算模型适用性验证'
        })
    for name,rows in [('design_cases.jsonl',design),('user_requests.jsonl',requests)]:
        (DATA/'data'/name).write_text(''.join(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n' for row in rows),encoding='utf-8')
    with (DATA/'review'/'case_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(review[0]));writer.writeheader();writer.writerows(review)
    return len(design),len(requests)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--robas-archive',type=Path,required=True)
    args=p.parse_args()
    print('GENERATED',generate(args.robas_archive))
