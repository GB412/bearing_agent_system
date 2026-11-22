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


# New cases DGB-0025..DGB-0080. Their operating conditions, targets and
# installation choices are synthetic and NOT reviewed for engineering feasibility.
CASES += [
 # Same model under substantially different synthetic operating conditions.
 spec("6205","变频电机低速巡航工况",2800,0,750,0,48,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("L10h",">=",18000,"h"),("power_loss_w","<=",9,"W")]),
 spec("6205","驱动电机较高径向载荷工况",7400,0,2400,320,82,"渗碳轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",25000,"h"),("temperature_rise_c","<=",28,"degC")],"boundDw"),
 spec("6205","伺服电机短时高速运行点",17500,0,450,100,72,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",24,"degC"),("power_loss_w","<=",14,"W")],"lockZ"),
 spec("6205","小型泵长时间连续运行",4200,0,1050,160,68,"渗碳轴承钢","VG46","C3","m5/H7","maximize_L10h",[("L10h",">=",50000,"h")],"boundDpw"),
 spec("6206","风机电机轻载模式",16000,0,320,0,64,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",22000,"h")],"boundFo"),
 spec("6206","输送线频繁运行的等效稳态点",3600,0,3100,210,74,"渗碳轴承钢","VG68","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",28000,"h"),("peak_contact_pressure_mpa","<=",1900,"MPa")],"lockZ_boundDw"),
 spec("6206","水泵驱动高转速点",11800,0,1500,260,80,"氮共渗轴承钢","VG46","C3","k5/H7","minimize_peak_contact_pressure",[("L10h",">=",22000,"h")],"boundFiFo"),
 spec("6206","电机工况切换后的低速设计点",2300,0,1800,0,53,"渗碳轴承钢","VG100","CN","m5/H7","maximize_L10h",[("L10h",">=",42000,"h"),("power_loss_w","<=",23,"W")]),
 spec("6004","微型泵轴轻载高速方案",22000,0,100,20,60,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",14000,"h")],"boundCurvature"),
 spec("6004","实验设备低转速轴承工况",2200,0,850,0,45,"渗碳轴承钢","VG68","CN","m5/H7","maximize_L10h",[("L10h",">=",30000,"h")]),
 spec("6004","小型风机持续热运行点",9000,0,540,95,85,"氮共渗轴承钢","VG32","C3","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",20,"degC"),("L10h",">=",18000,"h")],"boundCurvature"),
 spec("6305","工业转盘低速承载点",900,0,6000,350,75,"渗碳轴承钢","VG100","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",1700,"MPa"),("L10h",">=",30000,"h")],"boundFiFo"),
 spec("6305","中型减速装置转轴支承",4200,0,2900,600,86,"氮共渗轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",32000,"h")],"boundFo"),
 spec("6305","通用电机中速轻载设计点",6500,0,550,40,60,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("power_loss_w","<=",12,"W"),("temperature_rise_c","<=",22,"degC")]),
 spec("6308","搅拌传动低速大径向载荷",800,0,14500,1200,93,"渗碳轴承钢","VG100","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",20000,"h"),("peak_contact_pressure_mpa","<=",2100,"MPa")],"boundFiFo"),
 spec("6308","大功率风机转轴中速负载点",3500,0,7000,250,86,"氮共渗轴承钢","VG68","C3","m5/H7","minimize_power_loss",[("power_loss_w","<=",42,"W"),("L10h",">=",25000,"h")],"boundFiFo"),
 spec("6006","电动工具低载启动后稳态",14000,0,220,50,58,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_temperature_rise",[("L10h",">=",12000,"h"),("temperature_rise_c","<=",16,"degC")],"boundFo"),
 spec("6006","紧凑电机高载转轴设计点",5800,0,2100,450,79,"渗碳轴承钢","VG68","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",19000,"h")]),
 spec("6208","减速机构高载低速方案",1200,0,9800,750,89,"渗碳轴承钢","VG100","C3","m5/H7","maximize_L10h",[("L10h",">=",35000,"h"),("peak_contact_pressure_mpa","<=",1800,"MPa")],"lockZ"),
 spec("6208","通风机中速定转速点",6800,0,1700,0,65,"氮共渗轴承钢","VG46","CN","k5/H7","minimize_power_loss",[("L10h",">=",28000,"h")],"boundFo"),
 spec("6203","轻型传动电机中速运行",7200,0,620,90,66,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("power_loss_w","<=",7,"W"),("L10h",">=",15000,"h")],"boundDpw"),
 spec("6203","微型齿轮组件低速受载",1700,0,1600,210,56,"渗碳轴承钢","VG68","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",1650,"MPa")],"lockZ_boundFo"),
 spec("6008","制冷装置风机高速工况",15000,0,650,75,77,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",18,"degC"),("power_loss_w","<=",14,"W")]),
 spec("6008","工业机械中速高载点",4900,0,3900,180,83,"渗碳轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",36000,"h")],"boundFiFo"),
 # Different sizes: 6000 / 6200 / 6300 series from DGBData.db.
 spec("6009","精密风机转轴支承",9700,0,880,160,72,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("L10h",">=",24000,"h"),("temperature_rise_c","<=",25,"degC")]),
 spec("6010","小型水泵连续运行支承",7800,0,1800,250,79,"渗碳轴承钢","VG46","C3","m5/H7","maximize_L10h",[("L10h",">=",32000,"h"),("power_loss_w","<=",34,"W")],"boundFo"),
 spec("6011","轻型机械传动轴承",4200,0,3400,0,68,"渗碳轴承钢","VG68","CN","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",1850,"MPa")]),
 spec("6012","设备传动箱辅助支承",3800,0,4300,410,81,"氮共渗轴承钢","VG68","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",38000,"h"),("power_loss_w","<=",40,"W")],"boundFiFo"),
 spec("6200","微型直流驱动轮轴承",13000,0,90,0,50,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",16000,"h")],"boundCurvature"),
 spec("6201","紧凑型清洗泵支承",11000,0,220,45,64,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_temperature_rise",[("L10h",">=",18000,"h"),("temperature_rise_c","<=",20,"degC")],"boundDw"),
 spec("6211","中型电机定速工作点",5200,0,4100,380,76,"渗碳轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",30000,"h")],"lockZ"),
 spec("6212","输送机传动轴支承",2600,0,6800,520,86,"渗碳轴承钢","VG100","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",1950,"MPa"),("L10h",">=",26000,"h")],"boundFiFo"),
 spec("6213","工业风机大型辅助转轴",3400,0,4800,0,80,"氮共渗轴承钢","VG46","CN","k5/H7","minimize_power_loss",[("power_loss_w","<=",38,"W")],"boundCurvature"),
 spec("6214","中型输油泵负载侧",2100,0,9300,760,92,"渗碳轴承钢","VG100","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",40000,"h"),("peak_contact_pressure_mpa","<=",2200,"MPa")],"boundFo"),
 spec("6300","小型工业电机前端",8200,0,380,60,58,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",12000,"h")]),
 spec("6301","轻型传动结构径向轴承",6400,0,650,90,62,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",21,"degC")],"boundFo"),
 spec("6302","小型循环装置轴承",5000,0,1400,180,75,"渗碳轴承钢","VG46","C3","m5/H7","maximize_L10h",[("L10h",">=",21000,"h"),("power_loss_w","<=",16,"W")],"boundCurvature"),
 spec("6303","轻型减速器传动端",2900,0,2600,320,82,"渗碳轴承钢","VG68","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",1750,"MPa"),("temperature_rise_c","<=",27,"degC")],"boundFiFo"),
 spec("6309","大直径工业风机转子",2800,0,8600,640,85,"氮共渗轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",40000,"h")],"boundCurvature"),
 spec("6310","中型工业搅拌设备",1700,0,12500,1500,96,"渗碳轴承钢","VG100","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",2250,"MPa")],"boundFo"),
 spec("6311","重载传动机构支承",1250,0,16000,1100,94,"渗碳轴承钢","VG100","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",42000,"h"),("power_loss_w","<=",54,"W")],"boundFiFo"),
 spec("6312","大功率工业机械转轴",950,0,17500,0,90,"渗碳轴承钢","VG100","C3","m5/H7","maximize_L10h",[("L10h",">=",45000,"h")],"boundFiFo"),
 # Mixed hard constraints / additional small bearing variants.
 spec("6007","高速送风机受限功耗工况",16500,0,620,90,78,"氮共渗轴承钢","VG32","C3","k5/H7","minimize_power_loss",[("L10h",">=",22000,"h"),("power_loss_w","<=",11,"W"),("temperature_rise_c","<=",23,"degC")],"boundFo"),
 spec("6207","齿轮箱寿命与接触约束设计",3800,0,4600,780,88,"渗碳轴承钢","VG100","C3","m5/H7","maximize_L10h",[("L10h",">=",35000,"h"),("peak_contact_pressure_mpa","<=",1900,"MPa"),("power_loss_w","<=",35,"W")],"lockZ_boundDw"),
 spec("6005","小型高速驱动低温升需求",19000,0,380,45,81,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_temperature_rise",[("L10h",">=",16000,"h"),("temperature_rise_c","<=",19,"degC"),("power_loss_w","<=",7,"W")],"boundFiFo"),
 spec("6306","泵轴径向刚度优先设计点",5200,0,4500,680,89,"渗碳轴承钢","VG68","C3","m5/H7","maximize_radial_stiffness",[("L10h",">=",31000,"h"),("peak_contact_pressure_mpa","<=",2000,"MPa"),("temperature_rise_c","<=",30,"degC")],"boundFiFo"),
 spec("6209","负载侧轴承综合约束方案",3100,0,7300,660,92,"渗碳轴承钢","VG100","C3","m5/H7","minimize_power_loss",[("L10h",">=",27000,"h"),("power_loss_w","<=",38,"W"),("peak_contact_pressure_mpa","<=",2000,"MPa")],"boundDpw"),
 spec("6003","紧凑电机最高功耗限制",15500,0,220,0,62,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("power_loss_w","<=",6,"W"),("temperature_rise_c","<=",18,"degC")],"boundFiFo"),
 spec("6204","中载电机寿命与散热兼顾",8000,0,1250,160,79,"氮共渗轴承钢","VG46","CN","k5/H7","maximize_L10h",[("L10h",">=",24000,"h"),("temperature_rise_c","<=",22,"degC"),("power_loss_w","<=",18,"W")],"boundFo"),
 spec("6307","机械传动端接触压力上限",2600,0,7200,900,91,"渗碳轴承钢","VG100","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",1800,"MPa"),("L10h",">=",30000,"h")],"boundFiFo"),
 spec("6202","小型输送机轻载低功耗工况",4000,0,440,70,54,"氮共渗轴承钢","VG32","CN","k5/H7","minimize_power_loss",[("power_loss_w","<=",8,"W"),("L10h",">=",22000,"h")],"boundDpw"),
 spec("6001","小尺寸高速测试轴承",28000,0,75,5,64,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_temperature_rise",[("temperature_rise_c","<=",14,"degC"),("L10h",">=",12000,"h")],"boundFo"),
 spec("6210","运行效率与寿命双要求",4500,0,5600,300,87,"渗碳轴承钢","VG68","C3","m5/H7","maximize_L10h",[("L10h",">=",36000,"h"),("power_loss_w","<=",32,"W")],"boundFiFo"),
 spec("6304","装配空间受限的旋转驱动",6800,0,1450,240,76,"氮共渗轴承钢","VG46","CN","k5/H7","maximize_radial_stiffness",[("L10h",">=",24000,"h"),("peak_contact_pressure_mpa","<=",1750,"MPa")],"boundFiFo"),
 spec("6002","低载高速仪器轴承方案",18000,0,110,15,58,"氮共渗轴承钢","VG22","CN","k5/H7","minimize_power_loss",[("L10h",">=",14000,"h"),("power_loss_w","<=",5,"W")],"boundFo"),
 spec("6212","大型输送机构高载工作点",1900,0,12500,900,95,"渗碳轴承钢","VG100","C3","m5/H7","minimize_peak_contact_pressure",[("peak_contact_pressure_mpa","<=",2100,"MPa"),("L10h",">=",28000,"h")],"lockZ_boundDw"),
]
assert len(CASES)==80, f"Expected 80 design cases, got {len(CASES)}"

# Ten distinct single-message linguistic styles, eight cases per style.
LANGUAGE_STYLES = [
 '工程技术交底','日常口语','项目委托','参数清单','目标先行',
 '简明压缩','约束先行','现场说明','设计复核','工况先行'
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
    """Single-shot *complete* user demand in one of ten deterministic styles.

    Explicitly mentioned fields must agree with structured target.  RoBAS physical
    properties are catalog-side data, not falsely attributed to ordinary users.
    """
    b, op, en, r, opt = (c[k] for k in ('bearing','operating','engineering','requirements','optimization'))
    d=c['dimensions']
    style=LANGUAGE_STYLES[(idx-1) % len(LANGUAGE_STYLES)]
    app=b['application'];model=b['reference_model']
    dim=f"{d['d_mm']:g}×{d['D_mm']:g}×{d['B_mm']:g} mm"
    speeds=f"内圈{op['inner_speed_rpm']:g} rpm，外圈{op['outer_speed_rpm']:g} rpm（固定）"
    fr=f"径向载荷Fr={op['radial_load_n']:g} N"
    if op['axial_load_n']==0:
        fa=f"轴向载荷Fa=0 N（明确没有轴向载荷）"
    else:
        fa=f"轴向载荷Fa={op['axial_load_n']:g} N（沿轴线由电机侧指向负载侧）"
    tmp=f"假定轴承工作温度{op['temperature_c']:g}℃"
    directions='径向载荷方向竖直向下；从电机侧观察内圈顺时针旋转'
    materials=(f"内、外圈和钢球均选RoBAS目录中的{en['inner_ring_material']}，"
               f"保持架为{en['cage_type']}、材料{en['cage_material']}")
    oil=f"油润滑，润滑剂为RoBAS目录中的{en['lubricant']}"
    fit=f"游隙组选{en['clearance_group']}（未指定具体毫米游隙）；轴配合{en['shaft_fit']}，座孔配合{en['housing_fit']}"
    aim=OBJECTIVES[r['objective']]
    req=', '.join(CONSTRAINTS[e['metric']](e['value'],e['unit']) for e in r['constraints'])
    labels={'Dw_mm':'钢球直径Dw','Z':'钢球数量Z','Dpw_mm':'钢球节圆直径Dpw',
            'fi':'内沟曲率系数fi','fo':'外沟曲率系数fo'}
    restrictions=[]
    for key,val in opt['locked'].items():
        restrictions.append(f"{labels[key]}固定为{val:g}")
    for key,bd in opt['bounds'].items():
        units=' mm' if key in ('Dw_mm','Dpw_mm') else ''
        restrictions.append(f"{labels[key]}限制在{bd['min']:g}至{bd['max']:g}{units}")
    if restrictions:
        optimization='；'.join(restrictions)+'；其他未锁定的变量从Dw、Z、Dpw、fi、fo中优化确定'
    else:
        optimization='Dw、Z、Dpw、fi、fo这五个内部结构参数全部留给后续优化'
    caution='这些材料、润滑、保持架、游隙和配合仅是待审核的选择，须核实工程适用性，不等于已通过RoBAS求解。'
    envelope=f"单列深沟球轴承，参考RoBAS型号{model}，外形固定为{dim}，内部结构允许重设计"
    cond=f"{speeds}；单个轴承{fr}、{fa}；{tmp}；{directions}"
    mat=f"{materials}；{oil}；{fit}"
    goal=f"设计目标：{aim}；同时满足{req}"
    opttxt=f"内部参数：{optimization}"
    if style=='工程技术交底':
        text=(f"为{app}制定单列深沟球轴承的结构设计输入。外形采用RoBAS {model}的{dim}，只固定d、D、B，不沿用内部滚动体结构。"
              f"分析工况如下：{cond}。\n工程选型：{mat}。\n技术指标：{aim}，硬约束为{req}。{opttxt}。{caution}")
    elif style=='日常口语':
        text=(f"我这边要给{app}配个单列深沟球轴承，打算按RoBAS里的{model}来，尺寸就定{dim}，球和沟道那些可以重新设计。"
              f"机器运行时{speeds}，一个轴承受{fr}，另外还有{fa}，{tmp}。{directions}。"
              f"材料我先定{materials}，润滑用{oil}；装配方面{fit}。我更希望{aim}，但{req}也必须考虑。"
              f"{optimization}。{caution}")
    elif style=='项目委托':
        text=(f"设计委托：请为“{app}”形成一份深沟球轴承参数方案。外形基准RoBAS {model}，d×D×B={dim}，不限制内部几何重设计。"
              f"请按{cond}作为本次单一稳态分析条件。暂选{mat}。"
              f"交付要求是{aim}，并满足{req}；{optimization}。"
              f"请特别注明：选定的数据库条目只表明来源可查，组合的工程适用性仍待审查。")
    elif style=='参数清单':
        text=(f"深沟球轴承设计参数汇总（用于{app}）：\n"
              f"- 型号与外形：RoBAS {model}，{dim}，固定外形但内部可改；\n"
              f"- 工况：{cond}；\n- 零件材料及润滑：{materials}；{oil}；\n"
              f"- 游隙/配合：{fit}；\n- 优化目标：{aim}；约束：{req}；\n"
              f"- 五参数：{optimization}。\n上述工程选型尚未进行适用性与求解审核。")
    elif style=='目标先行':
        text=(f"这次最看重的是{aim}，但有几条不能忽略的要求：{req}。"
              f"对象是{app}使用的单列深沟球轴承，RoBAS型号{model}的{dim}外形不能改，内部球径、球数等可以调。"
              f"实际设计分析点为{cond}。材料、润滑及装配先按以下选项：{mat}。"
              f"优化的自由度这样设定：{optimization}。{caution}")
    elif style=='简明压缩':
        text=(f"做{app}的深沟球轴承：RoBAS {model}、外形{dim}固定、内部几何可优化。"
              f"{cond}。{mat}。主要{aim}，约束{req}。{optimization}。"
              f"提醒：工程组合仅为待审核候选，未做真实求解。")
    elif style=='约束先行':
        text=(f"先明确设计边界：{req}；最终希望{aim}。"
              f"轴承用于{app}，类型为单列深沟球，参照RoBAS {model}，安装外形锁定{dim}，只优化内部结构。"
              f"规定的运行点：{cond}。配置条件：{mat}。"
              f"五变量处理方式为{optimization}。{caution}")
    elif style=='现场说明':
        text=(f"现场要考虑的是{app}，我们想用单列深沟球轴承，外形空间按RoBAS {model}的{dim}预留好了。"
              f"这次只做一个稳态工况：{cond}。"
              f"先把选材和安装意见写清楚：{mat}。"
              f"希望{aim}，同时要求{req}。球径、球数和沟道的优化规则为：{optimization}。"
              f"这些配置只代表待核验的设计意向，不能当作RoBAS已经算通过。")
    elif style=='设计复核':
        text=(f"请按下面信息建立一个待复核的深沟球轴承需求，不要把候选配置直接视作可行解。应用为{app}。"
              f"RoBAS目录参考{model}，固定{dim}的外形尺寸，内部设计不随型号锁定。"
              f"工况输入：{cond}。材料润滑和配合记录：{mat}。"
              f"最终要优化{aim}，约束检查项是{req}。{opttxt}。"
              f"工程适用性和求解器兼容性后续另行审核。")
    else: # 工况先行
        text=(f"有一个需要单独分析的工况：{cond}。"
              f"这是{app}所用的单列深沟球轴承，外形取RoBAS {model}对应的{dim}，尺寸不变但内部允许重新选取。"
              f"工程设置暂定{mat}。性能方面{req}是约束，{aim}是优化目标。"
              f"关于五个结构参数，{optimization}。{caution}")
    return style,text



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
        elif s['opt']=='boundDpw':
            if ref is None: raise ValueError(f'No verified Dpw for {mid}')
            dpw=float(ref['Dwp'])
            o['bounds']['Dpw_mm']={'min':round(dpw*0.96,3),'max':round(dpw*1.04,3)}
        elif s['opt']=='boundFo':
            o['bounds']['fo']={'min':0.52,'max':0.56}
        elif s['opt']=='boundFiFo':
            o['bounds']['fi']={'min':0.51,'max':0.54}
            o['bounds']['fo']={'min':0.52,'max':0.56}
        elif s['opt'] in {'lockZ_boundDw','lockZ_boundFo'}:
            if ref is None: raise ValueError(f'No verified Z for {mid}')
            o['locked']['Z']=int(ref['Z']);o['variables'].remove('Z')
            if s['opt']=='lockZ_boundDw':
                dw=float(ref['Dw'])
                o['bounds']['Dw_mm']={'min':round(dw*0.92,3),'max':round(dw*1.08,3)}
            else:
                o['bounds']['fo']={'min':0.52,'max':0.56}
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
        style, natural_text=assemble_request(record,idx)
        request={'record_type':'user_request','request_id':f'REQ-{idx:04d}',
                 'case_id':record['case_id'],'language_style':style,'text':natural_text}
        design.append(record);requests.append(request)
        review.append({
          'case_id':record['case_id'],'application':s['app'],'reference_model':mid,
          'd_mm':m['d'],'D_mm':m['Dd'],'B_mm':m['B'],
          'inner_speed_rpm':s['ni'],'outer_speed_rpm':s['no'],
          'Fr_N':s['fr'],'Fa_N':s['fa'],'temperature_c':s['temp'],
          'objective':s['obj'],'optimization_mode':s['opt'],'language_style':style,
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
