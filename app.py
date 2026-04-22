import streamlit as st
import numpy as np
import plotly.graph_objects as go
import pandas as pd
import json
import time
import streamlit.components.v1 as components
from CoolProp.CoolProp import PropsSI
try:
    import google.generativeai as genai
except ImportError:
    genai = None


try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    GEMINI_API_KEY = None

if genai is not None and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 设置页面配置
st.set_page_config(
    page_title="交互式制冷循环分析工具",
    page_icon="❄️",
    layout="wide"
)

# 页面标题
st.title("交互式制冷循环分析工具")

st.markdown(
    """
    <style>
    .ai-result-card {
        border: 1px solid #dbe4ff;
        border-left: 6px solid #2b6cff;
        border-radius: 12px;
        padding: 16px 18px;
        background: linear-gradient(180deg, #f8fbff 0%, #f2f7ff 100%);
        margin-top: 8px;
        margin-bottom: 10px;
    }
    .ai-result-title {
        font-weight: 700;
        font-size: 1.05rem;
        margin-bottom: 8px;
        color: #163a8a;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 侧边栏输入
st.sidebar.header("输入参数")

# 制冷剂选择
refrigerant = st.sidebar.selectbox(
    "制冷剂",
    options=["R134a", "R717", "R22", "R410A"],
    index=0
)

# 循环结构选择
cycle_type = st.sidebar.radio(
    "循环结构",
    options=["单级压缩循环", "带经济器的双级压缩循环"]
)

# 蒸发温度输入
T_evap = st.sidebar.slider(
    "蒸发温度 (°C)",
    min_value=-40.0,
    max_value=10.0,
    value=5.0,
    step=0.5
)

# 冷凝温度输入
T_cond = st.sidebar.slider(
    "冷凝温度 (°C)",
    min_value=20.0,
    max_value=60.0,
    value=40.0,
    step=0.5
)

# 图表样式设置
st.sidebar.markdown("---")
st.sidebar.subheader("图表样式")
show_saturation_dome = st.sidebar.checkbox("显示饱和罩边界", value=True)
dome_color = st.sidebar.color_picker("饱和罩颜色", "#808080")
dome_line_style_label = st.sidebar.selectbox(
    "饱和罩线型",
    options=["虚线", "点线", "实线"],
    index=0
)
dome_line_style_map = {
    "虚线": "dash",
    "点线": "dot",
    "实线": "solid"
}
dome_line_style = dome_line_style_map[dome_line_style_label]
dome_line_width = st.sidebar.slider("饱和罩线宽", min_value=0.5, max_value=4.0, value=1.5, step=0.1)
dome_opacity = st.sidebar.slider("饱和罩透明度", min_value=0.1, max_value=1.0, value=0.8, step=0.05)
dome_points = st.sidebar.slider("饱和罩采样点数", min_value=80, max_value=600, value=300, step=20)
process_points = st.sidebar.slider("循环过程采样点数", min_value=50, max_value=300, value=120, step=10)

# 中间压力输入（仅双级压缩）
if cycle_type == "带经济器的双级压缩循环":
    intermed_pressure_option = st.sidebar.radio(
        "中间压力设置",
        options=["使用经验公式计算", "手动输入"]
    )
    
    if intermed_pressure_option == "手动输入":
        # 计算默认中间压力（使用经验公式）
        P_evap = PropsSI('P', 'T', T_evap + 273.15, 'Q', 1, refrigerant)
        P_cond = PropsSI('P', 'T', T_cond + 273.15, 'Q', 0, refrigerant)
        P_intermed_default = np.sqrt(P_evap * P_cond)
        
        # 手动输入中间压力
        P_intermed = st.sidebar.number_input(
            "中间压力 (Pa)",
            value=P_intermed_default,
            step=1e5
        )
    else:
        # 使用经验公式计算中间压力
        P_evap = PropsSI('P', 'T', T_evap + 273.15, 'Q', 1, refrigerant)
        P_cond = PropsSI('P', 'T', T_cond + 273.15, 'Q', 0, refrigerant)
        P_intermed = np.sqrt(P_evap * P_cond)
        st.sidebar.info(f"计算的中间压力: {P_intermed:.2e} Pa")

# 热力学计算函数
def calculate_single_stage_cycle():
    """计算单级压缩循环的状态点"""
    # 状态点1: 蒸发器出口，饱和蒸汽
    T1 = T_evap + 273.15  # K
    P1 = PropsSI('P', 'T', T1, 'Q', 1, refrigerant)
    h1 = PropsSI('H', 'T', T1, 'Q', 1, refrigerant)
    s1 = PropsSI('S', 'T', T1, 'Q', 1, refrigerant)
    x1 = 1.0  # 干度
    
    # 状态点2: 压缩机出口，等熵压缩到冷凝压力
    P2 = PropsSI('P', 'T', T_cond + 273.15, 'Q', 0, refrigerant)
    s2 = s1  # 等熵过程
    h2 = PropsSI('H', 'P', P2, 'S', s2, refrigerant)
    T2 = PropsSI('T', 'P', P2, 'S', s2, refrigerant)
    x2 = None  # 过热蒸汽
    
    # 状态点3: 冷凝器出口，饱和液体
    T3 = T_cond + 273.15  # K
    P3 = P2
    h3 = PropsSI('H', 'T', T3, 'Q', 0, refrigerant)
    s3 = PropsSI('S', 'T', T3, 'Q', 0, refrigerant)
    x3 = 0.0  # 干度
    
    # 状态点4: 节流阀出口，等焓节流到蒸发压力
    P4 = P1
    h4 = h3  # 等焓过程
    T4 = PropsSI('T', 'P', P4, 'H', h4, refrigerant)
    s4 = PropsSI('S', 'P', P4, 'H', h4, refrigerant)
    x4 = PropsSI('Q', 'P', P4, 'H', h4, refrigerant)  # 干度
    
    # 计算性能指标
    q0 = h1 - h4  # 制冷量 (J/kg)
    w = h2 - h1  # 压缩机耗功 (J/kg)
    cop = q0 / w  # 性能系数
    
    # 整理状态点数据
    states = [
        {"点": 1, "P (Pa)": P1, "T (°C)": T1 - 273.15, "h (J/kg)": h1, "s (J/kg·K)": s1, "x": x1},
        {"点": 2, "P (Pa)": P2, "T (°C)": T2 - 273.15, "h (J/kg)": h2, "s (J/kg·K)": s2, "x": x2},
        {"点": 3, "P (Pa)": P3, "T (°C)": T3 - 273.15, "h (J/kg)": h3, "s (J/kg·K)": s3, "x": x3},
        {"点": 4, "P (Pa)": P4, "T (°C)": T4 - 273.15, "h (J/kg)": h4, "s (J/kg·K)": s4, "x": x4}
    ]
    
    return states, q0, w, cop

def calculate_two_stage_cycle():
    """计算带经济器的双级压缩循环的状态点"""
    # 状态点1: 蒸发器出口，饱和蒸汽
    T1 = T_evap + 273.15  # K
    P1 = PropsSI('P', 'T', T1, 'Q', 1, refrigerant)
    h1 = PropsSI('H', 'T', T1, 'Q', 1, refrigerant)
    s1 = PropsSI('S', 'T', T1, 'Q', 1, refrigerant)
    x1 = 1.0  # 干度
    
    # 状态点2: 低压级压缩机出口，等熵压缩到中间压力
    P2 = P_intermed
    s2 = s1  # 等熵过程
    h2 = PropsSI('H', 'P', P2, 'S', s2, refrigerant)
    T2 = PropsSI('T', 'P', P2, 'S', s2, refrigerant)
    x2 = None  # 过热蒸汽
    
    # 状态点3: 冷凝器出口，饱和液体
    T3 = T_cond + 273.15  # K
    P3 = PropsSI('P', 'T', T3, 'Q', 0, refrigerant)
    h3 = PropsSI('H', 'T', T3, 'Q', 0, refrigerant)
    s3 = PropsSI('S', 'T', T3, 'Q', 0, refrigerant)
    x3 = 0.0  # 干度
    
    # 状态点4: 第一节流阀出口，等焓节流到中间压力
    P4 = P_intermed
    h4 = h3  # 等焓过程
    T4 = PropsSI('T', 'P', P4, 'H', h4, refrigerant)
    s4 = PropsSI('S', 'P', P4, 'H', h4, refrigerant)
    x4 = PropsSI('Q', 'P', P4, 'H', h4, refrigerant)  # 干度
    
    # 状态点5: 经济器出口，饱和蒸汽
    T5 = T4
    P5 = P4
    h5 = PropsSI('H', 'T', T5, 'Q', 1, refrigerant)
    s5 = PropsSI('S', 'T', T5, 'Q', 1, refrigerant)
    x5 = 1.0  # 干度
    
    # 状态点6: 高压级压缩机入口，低压级出口与经济器出口混合
    h6 = (h2 + h5) / 2  # 假设质量流量相等
    P6 = P_intermed
    T6 = PropsSI('T', 'P', P6, 'H', h6, refrigerant)
    s6 = PropsSI('S', 'P', P6, 'H', h6, refrigerant)
    x6 = None  # 过热蒸汽
    
    # 状态点7: 高压级压缩机出口，等熵压缩到冷凝压力
    P7 = P3
    s7 = s6  # 等熵过程
    h7 = PropsSI('H', 'P', P7, 'S', s7, refrigerant)
    T7 = PropsSI('T', 'P', P7, 'S', s7, refrigerant)
    x7 = None  # 过热蒸汽
    
    # 状态点8: 第二节流阀出口，等焓节流到蒸发压力
    P8 = P1
    h8 = PropsSI('H', 'T', T4, 'Q', 0, refrigerant)  # 经济器出口饱和液体
    T8 = PropsSI('T', 'P', P8, 'H', h8, refrigerant)
    s8 = PropsSI('S', 'P', P8, 'H', h8, refrigerant)
    x8 = PropsSI('Q', 'P', P8, 'H', h8, refrigerant)  # 干度
    
    # 计算性能指标
    q0 = h1 - h8  # 制冷量 (J/kg)
    w = (h2 - h1) + (h7 - h6)  # 压缩机总耗功 (J/kg)
    cop = q0 / w  # 性能系数
    
    # 整理状态点数据
    states = [
        {"点": 1, "P (Pa)": P1, "T (°C)": T1 - 273.15, "h (J/kg)": h1, "s (J/kg·K)": s1, "x": x1},
        {"点": 2, "P (Pa)": P2, "T (°C)": T2 - 273.15, "h (J/kg)": h2, "s (J/kg·K)": s2, "x": x2},
        {"点": 3, "P (Pa)": P3, "T (°C)": T3 - 273.15, "h (J/kg)": h3, "s (J/kg·K)": s3, "x": x3},
        {"点": 4, "P (Pa)": P4, "T (°C)": T4 - 273.15, "h (J/kg)": h4, "s (J/kg·K)": s4, "x": x4},
        {"点": 5, "P (Pa)": P5, "T (°C)": T5 - 273.15, "h (J/kg)": h5, "s (J/kg·K)": s5, "x": x5},
        {"点": 6, "P (Pa)": P6, "T (°C)": T6 - 273.15, "h (J/kg)": h6, "s (J/kg·K)": s6, "x": x6},
        {"点": 7, "P (Pa)": P7, "T (°C)": T7 - 273.15, "h (J/kg)": h7, "s (J/kg·K)": s7, "x": x7},
        {"点": 8, "P (Pa)": P8, "T (°C)": T8 - 273.15, "h (J/kg)": h8, "s (J/kg·K)": s8, "x": x8}
    ]
    
    return states, q0, w, cop

# 计算循环参数
if cycle_type == "单级压缩循环":
    states, q0, w, cop = calculate_single_stage_cycle()
else:
    states, q0, w, cop = calculate_two_stage_cycle()

# 生成三相点到临界点的饱和罩数据
def generate_saturation_dome_data(refrigerant, num_points=300):
    """返回制冷剂饱和液线(x=0)与饱和汽线(x=1)在 p-h 和 T-s 图所需数据。"""
    T_triple = PropsSI('Ttriple', refrigerant)
    T_crit = PropsSI('Tcrit', refrigerant)

    # 避免端点附近数值不稳定
    t_normalized = np.linspace(0, 1, num_points)
    T_range = T_crit - (T_crit - T_triple - 1e-3) * (1 - t_normalized)**3

    p_sat = []
    h_liquid = []
    h_vapor = []
    s_liquid = []
    s_vapor = []
    T_sat_c = []

    for T in T_range:
        try:
            p = PropsSI('P', 'T', T, 'Q', 0, refrigerant)
            h_l = PropsSI('H', 'T', T, 'Q', 0, refrigerant)
            h_v = PropsSI('H', 'T', T, 'Q', 1, refrigerant)
            s_l = PropsSI('S', 'T', T, 'Q', 0, refrigerant)
            s_v = PropsSI('S', 'T', T, 'Q', 1, refrigerant)

            if np.isfinite(p) and p > 0:
                p_sat.append(p)
                h_liquid.append(h_l)
                h_vapor.append(h_v)
                s_liquid.append(s_l)
                s_vapor.append(s_v)
                T_sat_c.append(T - 273.15)
        except Exception:
            continue

    return {
        'p_sat': p_sat,
        'h_liquid': h_liquid,
        'h_vapor': h_vapor,
        's_liquid': s_liquid,
        's_vapor': s_vapor,
        'T_sat_c': T_sat_c
    }


def _init_curve(name):
    return {"name": name, "P": [], "T_c": [], "h": [], "s": []}


def _append_curve_point(curve, p_val, t_k, h_val, s_val):
    if (
        np.isfinite(p_val) and p_val > 0 and
        np.isfinite(t_k) and
        np.isfinite(h_val) and
        np.isfinite(s_val)
    ):
        curve["P"].append(p_val)
        curve["T_c"].append(t_k - 273.15)
        curve["h"].append(h_val)
        curve["s"].append(s_val)


def get_process_path(state1, state2, process_type, refrigerant, num_points=50):
    """基于CoolProp计算单个过程段的密集轨迹点。"""
    path = {"P": [], "T": [], "T_c": [], "h": [], "s": []}
    sample_count = max(50, num_points)

    def append_point(p_val, t_k, h_val, s_val):
        if (
            np.isfinite(p_val) and p_val > 0 and
            np.isfinite(t_k) and
            np.isfinite(h_val) and
            np.isfinite(s_val)
        ):
            path["P"].append(p_val)
            path["T"].append(t_k)
            path["T_c"].append(t_k - 273.15)
            path["h"].append(h_val)
            path["s"].append(s_val)

    if process_type == "isentropic":
        s_const = state1["s (J/kg·K)"]
        h_samples = np.linspace(state1["h (J/kg)"], state2["h (J/kg)"], sample_count)
        for h_val in h_samples:
            try:
                p_val = PropsSI('P', 'S', s_const, 'H', h_val, refrigerant)
                t_k = PropsSI('T', 'S', s_const, 'H', h_val, refrigerant)
                s_val = PropsSI('S', 'P', p_val, 'H', h_val, refrigerant)
                append_point(p_val, t_k, h_val, s_val)
            except Exception:
                continue

    elif process_type == "isobaric":
        p_const = state1["P (Pa)"]
        h_start = state1["h (J/kg)"]
        h_end = state2["h (J/kg)"]
        h_samples = np.linspace(h_start, h_end, sample_count)
        for h_val in h_samples:
            try:
                t_k = PropsSI('T', 'P', p_const, 'H', h_val, refrigerant)
                s_val = PropsSI('S', 'P', p_const, 'H', h_val, refrigerant)
                append_point(p_const, t_k, h_val, s_val)
            except Exception:
                continue

    elif process_type == "isenthalpic":
        h_const = state1["h (J/kg)"]
        p_samples = np.linspace(state1["P (Pa)"], state2["P (Pa)"], sample_count)
        for p_val in p_samples:
            try:
                t_k = PropsSI('T', 'P', p_val, 'H', h_const, refrigerant)
                s_val = PropsSI('S', 'P', p_val, 'H', h_const, refrigerant)
                append_point(p_val, t_k, h_const, s_val)
            except Exception:
                continue

    return path


def sample_isobaric_curve_by_h(name, p_const, h_start, h_end, refrigerant, points_per_process):
    """等压过程：按焓插值，用(P,H)求T和S。"""
    curve = _init_curve(name)
    h_samples = np.linspace(h_start, h_end, max(50, points_per_process))
    for h_val in h_samples:
        try:
            t_k = PropsSI('T', 'P', p_const, 'H', h_val, refrigerant)
            s_val = PropsSI('S', 'P', p_const, 'H', h_val, refrigerant)
            _append_curve_point(curve, p_const, t_k, h_val, s_val)
        except Exception:
            continue
    return curve


def sample_isentropic_curve_by_h(name, s_const, h_start, h_end, refrigerant, points_per_process):
    """等熵过程：按焓插值，用(S,H)求P和T。"""
    curve = _init_curve(name)
    h_samples = np.linspace(h_start, h_end, max(50, points_per_process))
    for h_val in h_samples:
        try:
            p_val = PropsSI('P', 'S', s_const, 'H', h_val, refrigerant)
            t_k = PropsSI('T', 'S', s_const, 'H', h_val, refrigerant)
            s_val = PropsSI('S', 'P', p_val, 'H', h_val, refrigerant)
            _append_curve_point(curve, p_val, t_k, h_val, s_val)
        except Exception:
            continue
    return curve


def sample_isenthalpic_curve_by_p(name, h_const, p_start, p_end, refrigerant, points_per_process):
    """等焓过程：按压力插值，用(P,H)求T和S。"""
    curve = _init_curve(name)
    p_samples = np.linspace(p_start, p_end, max(50, points_per_process))
    for p_val in p_samples:
        try:
            t_k = PropsSI('T', 'P', p_val, 'H', h_const, refrigerant)
            s_val = PropsSI('S', 'P', p_val, 'H', h_const, refrigerant)
            _append_curve_point(curve, p_val, t_k, h_const, s_val)
        except Exception:
            continue
    return curve


def build_single_stage_process_curves(states, refrigerant, points_per_process=120):
    """单级循环：所有可变焓过程均按焓插值并用CoolProp反算轨迹。"""
    state_map = {state["点"]: state for state in states}
    required_points = [1, 2, 3, 4]
    if any(point not in state_map for point in required_points):
        return []

    st1, st2, st3, st4 = (state_map[1], state_map[2], state_map[3], state_map[4])

    curves = [
        sample_isentropic_curve_by_h(
            name="1→2 等熵压缩",
            s_const=st1["s (J/kg·K)"],
            h_start=st1["h (J/kg)"],
            h_end=st2["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="2→3 等压冷凝",
            p_const=st2["P (Pa)"],
            h_start=st2["h (J/kg)"],
            h_end=st3["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isenthalpic_curve_by_p(
            name="3→4 等焓节流",
            h_const=st3["h (J/kg)"],
            p_start=st3["P (Pa)"],
            p_end=st4["P (Pa)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="4→1 等压蒸发",
            p_const=st4["P (Pa)"],
            h_start=st4["h (J/kg)"],
            h_end=st1["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        )
    ]

    return [curve for curve in curves if len(curve["h"]) >= 2]


def build_two_stage_process_curves(states, refrigerant, points_per_process=120):
    """双级循环：沿各过程物理约束生成由CoolProp驱动的密集轨迹。"""
    state_map = {state["点"]: state for state in states}
    required_points = [1, 2, 3, 4, 5, 6, 7, 8]
    if any(point not in state_map for point in required_points):
        return []

    st1 = state_map[1]
    st2 = state_map[2]
    st3 = state_map[3]
    st4 = state_map[4]
    st5 = state_map[5]
    st6 = state_map[6]
    st7 = state_map[7]
    st8 = state_map[8]

    curves = [
        sample_isentropic_curve_by_h(
            name="1→2 低压级等熵压缩",
            s_const=st1["s (J/kg·K)"],
            h_start=st1["h (J/kg)"],
            h_end=st2["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="2→6 中压等压混合",
            p_const=st2["P (Pa)"],
            h_start=st2["h (J/kg)"],
            h_end=st6["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isentropic_curve_by_h(
            name="6→7 高压级等熵压缩",
            s_const=st6["s (J/kg·K)"],
            h_start=st6["h (J/kg)"],
            h_end=st7["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="7→3 等压冷凝",
            p_const=st7["P (Pa)"],
            h_start=st7["h (J/kg)"],
            h_end=st3["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isenthalpic_curve_by_p(
            name="3→4 第一节流阀等焓",
            h_const=st3["h (J/kg)"],
            p_start=st3["P (Pa)"],
            p_end=st4["P (Pa)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="4→5 经济器等压蒸发",
            p_const=st4["P (Pa)"],
            h_start=st4["h (J/kg)"],
            h_end=st5["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="5→6 中压等压混合",
            p_const=st5["P (Pa)"],
            h_start=st5["h (J/kg)"],
            h_end=st6["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isenthalpic_curve_by_p(
            name="液支路→8 第二节流阀等焓",
            h_const=st8["h (J/kg)"],
            p_start=st4["P (Pa)"],
            p_end=st8["P (Pa)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        ),
        sample_isobaric_curve_by_h(
            name="8→1 等压蒸发",
            p_const=st8["P (Pa)"],
            h_start=st8["h (J/kg)"],
            h_end=st1["h (J/kg)"],
            refrigerant=refrigerant,
            points_per_process=points_per_process
        )
    ]

    return [curve for curve in curves if len(curve["h"]) >= 2]


def get_process_trace_style(process_name, cycle_type):
    """根据过程名称返回统一的颜色、线型和图例分组。"""
    if cycle_type == "单级压缩循环":
        mapping = {
            "1→2 等熵压缩": {"color": "#1f77b4", "dash": "solid", "group": "压缩"},
            "2→3 等压冷凝": {"color": "#d62728", "dash": "solid", "group": "冷凝"},
            "3→4 等焓节流": {"color": "#ff7f0e", "dash": "solid", "group": "节流"},
            "4→1 等压蒸发": {"color": "#2ca02c", "dash": "solid", "group": "蒸发"}
        }
        return mapping.get(process_name, {"color": "#7f7f7f", "dash": "solid", "group": "其它"})

    # 双级循环：主回路与支路使用不同视觉语义
    if "等熵压缩" in process_name:
        return {"color": "#1f77b4", "dash": "solid", "group": "压缩"}
    if "等压冷凝" in process_name:
        return {"color": "#d62728", "dash": "solid", "group": "冷凝"}
    if "等焓" in process_name:
        return {"color": "#ff7f0e", "dash": "solid", "group": "节流"}
    if "等压蒸发" in process_name and "经济器" in process_name:
        return {"color": "#17becf", "dash": "solid", "group": "经济器蒸发"}
    if "等压蒸发" in process_name:
        return {"color": "#2ca02c", "dash": "solid", "group": "蒸发器蒸发"}
    if "中压等压混合" in process_name:
        return {"color": "#9467bd", "dash": "dot", "group": "中压混合"}
    if "液支路" in process_name:
        return {"color": "#8c564b", "dash": "dashdot", "group": "液体支路"}
    return {"color": "#7f7f7f", "dash": "solid", "group": "其它"}


# 主界面显示
col_main, col_ai = st.columns([6, 4], gap="large")

saturation_dome = None
if show_saturation_dome:
    saturation_dome = generate_saturation_dome_data(refrigerant, num_points=dome_points)

with col_main:
    st.header("性能指标")

    # 使用st.metric展示关键性能指标
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        st.metric("制冷量", f"{q0/1000:.2f} kJ/kg")
    with metric_col2:
        st.metric("压缩机耗功", f"{w/1000:.2f} kJ/kg")
    with metric_col3:
        st.metric("理论COP", f"{cop:.2f}")

    # 绘制压焓图和温熵图
    st.header("循环图表")
    chart_col1, chart_col2 = st.columns(2)

    # 压焓图 (p-h图)
    with chart_col1:
        st.subheader("压焓图 (p-h图)")

        # 准备状态点数据
        h_values = [state["h (J/kg)"] for state in states]
        p_values = [state["P (Pa)"] for state in states]
        process_paths = []
        if cycle_type == "单级压缩循环":
            process_specs = [
                (0, 1, "isentropic", "1→2 等熵压缩"),
                (1, 2, "isobaric", "2→3 等压冷凝"),
                (2, 3, "isenthalpic", "3→4 等焓节流"),
                (3, 0, "isobaric", "4→1 等压蒸发")
            ]
            for start_idx, end_idx, process_type, process_name in process_specs:
                path = get_process_path(
                    states[start_idx],
                    states[end_idx],
                    process_type,
                    refrigerant,
                    num_points=process_points
                )
                path["name"] = process_name
                process_paths.append(path)
        else:
            process_paths = build_two_stage_process_curves(states, refrigerant, points_per_process=process_points)

        # 创建图形
        fig_ph = go.Figure()

        if show_saturation_dome and saturation_dome and len(saturation_dome['p_sat']) > 1:
            # 添加饱和罩（背景线）
            fig_ph.add_trace(go.Scatter(
                x=saturation_dome['h_liquid'],
                y=saturation_dome['p_sat'],
                mode='lines',
                name='饱和液体线',
                line=dict(color=dome_color, width=dome_line_width, dash=dome_line_style),
                opacity=dome_opacity
            ))

            # 添加饱和罩（背景线）
            fig_ph.add_trace(go.Scatter(
                x=saturation_dome['h_vapor'],
                y=saturation_dome['p_sat'],
                mode='lines',
                name='饱和蒸汽线',
                line=dict(color=dome_color, width=dome_line_width, dash=dome_line_style),
                opacity=dome_opacity
            ))

        if process_paths:
            for curve in process_paths:
                style = get_process_trace_style(curve["name"], cycle_type)
                fig_ph.add_trace(go.Scatter(
                    x=curve["h"],
                    y=curve["P"],
                    mode='lines',
                    name=curve["name"],
                    legendgroup=style["group"],
                    line=dict(width=2.5, color=style["color"], dash=style["dash"]),
                    hovertemplate='P: %{y:.2e} Pa<br>h: %{x:.2f} J/kg<br>s: %{customdata[0]:.2f} J/kg·K<br>T: %{customdata[1]:.2f} °C',
                    customdata=np.column_stack((curve["s"], curve["T_c"]))
                ))

        # 添加循环状态点
        fig_ph.add_trace(go.Scatter(
            x=h_values,
            y=p_values,
            mode='markers',
            name='状态点',
            marker=dict(size=8, color='green'),
            hovertemplate=
                '点 %{customdata[0]}<br>' +
                'P: %{y:.2e} Pa<br>' +
                'h: %{x:.2f} J/kg<br>' +
                'T: %{customdata[1]:.2f} °C<br>' +
                's: %{customdata[2]:.2f} J/kg·K',
            customdata=[[state["点"], state["T (°C)"], state["s (J/kg·K)"]] for state in states]
        ))

        # 设置布局
        fig_ph.update_layout(
            xaxis_title='焓 (J/kg)',
            yaxis_title='压力 (Pa)',
            yaxis_type='log',
            hovermode='closest',
            width=600,
            height=400
        )

        # 显示图形
        st.plotly_chart(fig_ph)

    # 温熵图 (T-s图)
    with chart_col2:
        st.subheader("温熵图 (T-s图)")

        # 准备状态点数据
        s_values = [state["s (J/kg·K)"] for state in states]
        T_values = [state["T (°C)"] + 273.15 for state in states]  # 转换为K

        # 创建图形
        fig_ts = go.Figure()

        if show_saturation_dome and saturation_dome and len(saturation_dome['T_sat_c']) > 1:
            # 添加饱和罩（背景线）
            fig_ts.add_trace(go.Scatter(
                x=saturation_dome['s_liquid'],
                y=saturation_dome['T_sat_c'],
                mode='lines',
                name='饱和液体线',
                line=dict(color=dome_color, width=dome_line_width, dash=dome_line_style),
                opacity=dome_opacity
            ))

            # 添加饱和罩（背景线）
            fig_ts.add_trace(go.Scatter(
                x=saturation_dome['s_vapor'],
                y=saturation_dome['T_sat_c'],
                mode='lines',
                name='饱和蒸汽线',
                line=dict(color=dome_color, width=dome_line_width, dash=dome_line_style),
                opacity=dome_opacity
            ))

        if process_paths:
            for curve in process_paths:
                style = get_process_trace_style(curve["name"], cycle_type)
                fig_ts.add_trace(go.Scatter(
                    x=curve["s"],
                    y=curve["T_c"],
                    mode='lines',
                    name=curve["name"],
                    legendgroup=style["group"],
                    line=dict(width=2.5, color=style["color"], dash=style["dash"]),
                    hovertemplate='T: %{y:.2f} °C<br>s: %{x:.2f} J/kg·K<br>P: %{customdata[0]:.2e} Pa<br>h: %{customdata[1]:.2f} J/kg',
                    customdata=np.column_stack((curve["P"], curve["h"]))
                ))

        # 添加循环状态点
        fig_ts.add_trace(go.Scatter(
            x=s_values,
            y=[T - 273.15 for T in T_values],  # 转换为°C
            mode='markers',
            name='状态点',
            marker=dict(size=8, color='green'),
            hovertemplate=
                '点 %{customdata[0]}<br>' +
                'T: %{y:.2f} °C<br>' +
                's: %{x:.2f} J/kg·K<br>' +
                'P: %{customdata[1]:.2e} Pa<br>' +
                'h: %{customdata[2]:.2f} J/kg',
            customdata=[[state["点"], state["P (Pa)"], state["h (J/kg)"]] for state in states]
        ))

        # 设置布局
        fig_ts.update_layout(
            xaxis_title='熵 (J/kg·K)',
            yaxis_title='温度 (°C)',
            hovermode='closest',
            width=600,
            height=400
        )

        # 显示图形
        st.plotly_chart(fig_ts)

    # 显示状态点数据表格
    st.header("状态点数据")

    def format_float(value, digits=2):
        return f"{value:.{digits}f}"

    def describe_state(row):
        x_value = row["x"]
        temperature_c = row["T (°C)"]
        pressure_pa = row["P (Pa)"]

        if x_value is not None and not pd.isna(x_value):
            if np.isclose(x_value, 1.0):
                return "饱和蒸汽"
            if np.isclose(x_value, 0.0):
                return "饱和液体"
            if 0.0 < x_value < 1.0:
                return f"湿蒸汽 (x={x_value:.2f})"

        try:
            t_sat_c = PropsSI('T', 'P', pressure_pa, 'Q', 0, refrigerant) - 273.15
            if temperature_c >= t_sat_c:
                return "过热蒸汽"
            return "过冷液体"
        except Exception:
            return "过热/过冷"

    df_states = pd.DataFrame(states)
    df_states_display = pd.DataFrame({
        "点": df_states["点"],
        "P (kPa)": df_states["P (Pa)"].apply(lambda value: format_float(value / 1000.0)),
        "T (°C)": df_states["T (°C)"].apply(format_float),
        "T (K)": df_states["T (°C)"].apply(lambda value: format_float(value + 273.15)),
        "h (J/kg)": df_states["h (J/kg)"].apply(format_float),
        "s (J/kg·K)": df_states["s (J/kg·K)"].apply(format_float),
        "状态描述": df_states.apply(describe_state, axis=1)
    })
    df_states_display = df_states_display[["点", "P (kPa)", "T (°C)", "T (K)", "h (J/kg)", "s (J/kg·K)", "状态描述"]]
    st.dataframe(df_states_display, use_container_width=True)

with col_ai:
    st.markdown("---")
    if st.button("🤖 让 AI 分析当前循环", type="primary", use_container_width=True):
        if genai is None:
            st.error("当前环境未安装 google-generativeai，请先执行 `pip install google-generativeai`。")
        elif not GEMINI_API_KEY:
            st.error("未找到 `st.secrets[\"GEMINI_API_KEY\"]`，请先配置 Gemini API Key。")
        else:
            prompt = (
                "请根据以下制冷循环参数，直接用中文分析当前工况的合理性，"
                "解释图像变化，并给出优化建议。"
                "不要自我介绍，不要使用‘同学们’等称呼。\n\n"
                f"制冷剂: {refrigerant}\n"
                f"循环类型: {cycle_type}\n"
                f"蒸发温度: {T_evap:.1f} °C\n"
                f"冷凝温度: {T_cond:.1f} °C\n"
            )

            if cycle_type == "带经济器的双级压缩循环":
                prompt += f"中间压力: {P_intermed / 1000.0:.2f} kPa\n"

            prompt += (
                f"制冷量: {q0 / 1000.0:.2f} kJ/kg\n"
                f"压缩机耗功: {w / 1000.0:.2f} kJ/kg\n"
                f"COP: {cop:.2f}\n\n"
                "请重点结合这些参数，说明循环是否接近合理运行区间，图上饱和罩、压焓图和温熵图可能反映出什么特征，"
                "以及从蒸发温度、冷凝温度、中间压力或压缩比角度提出可操作的优化建议。"
            )

            def stream_ai_reply(model_name):
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    prompt,
                    stream=True,
                    request_options={"timeout": 80}
                )
                started_output = False
                for chunk in response:
                    text = getattr(chunk, "text", None)
                    if text:
                        if not started_output:
                            started_output = True
                            progress_bar.progress(100, text="AI 已开始输出，进度 100%")
                            status_placeholder.success(f"{model_name} 已开始流式输出")
                        yield text

            st.subheader("AI 智能讲解")
            with st.container(height=750, border=False):
                status_placeholder = st.empty()
                ai_output_placeholder = st.empty()
                progress_bar = st.progress(5, text="正在初始化分析任务...")
                status_placeholder.info("最多等80秒，请耐心，出不来自然会报错")
                ai_reply_text = ""
                for progress_value, progress_text in [
                    (10, "正在整理循环参数..."),
                    (20, "正在连接 Gemini 模型..."),
                    (30, "模型请求已发送，最多等80秒，请耐心，出不来自然会报错"),
                ]:
                    progress_bar.progress(progress_value, text=progress_text)
                    time.sleep(0.15)
                try:
                    progress_bar.progress(35, text="已连接 gemini-3.1-flash-lite，最多等80秒，请耐心，出不来自然会报错")
                    ai_reply_text = st.write_stream(stream_ai_reply("gemini-3.1-flash-lite-preview"))
                except Exception:
                    st.error("Gemini 模型请求失败，请检查 API 配置或稍后重试。")
                    progress_bar.progress(0, text="模型请求失败")

                if isinstance(ai_reply_text, str) and ai_reply_text.strip():
                    progress_bar.progress(100, text="分析完成")
                    status_placeholder.success("AI 讲解已生成完成")
                    ai_output_placeholder.markdown(
                        f"""
                        <div class=\"ai-result-card\">
                            <div class=\"ai-result-title\">讲解摘要卡片</div>
                            <div>{ai_reply_text.replace(chr(10), '<br>')}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    copy_html = f"""
                    <div style=\"display:flex;align-items:center;gap:10px;margin:4px 0 0 0;\">
                        <button onclick='navigator.clipboard.writeText({json.dumps(ai_reply_text)}).then(function(){{document.getElementById("copy-status").innerText="已复制到剪贴板";}}).catch(function(){{document.getElementById("copy-status").innerText="复制失败，请手动复制";}})'
                            style='padding:8px 14px;border:1px solid #2b6cff;border-radius:8px;background:#2b6cff;color:#fff;font-weight:600;cursor:pointer;'>
                            复制讲解内容
                        </button>
                        <span id=\"copy-status\" style=\"color:#1f2937;font-size:13px;\"></span>
                    </div>
                    """
                    components.html(copy_html, height=52)
                else:
                    progress_bar.progress(100, text="本次未收到有效文本")
                    status_placeholder.warning("模型返回为空，请重试一次或缩短提示词。")

# 运行说明
st.sidebar.markdown("---")
st.sidebar.subheader("运行说明")
st.sidebar.markdown("1. 选择制冷剂类型")
st.sidebar.markdown("2. 选择循环结构")
st.sidebar.markdown("3. 调整蒸发温度和冷凝温度")
st.sidebar.markdown("4. 对于双级压缩，可选择中间压力设置方式")
st.sidebar.markdown("5. 主界面将实时显示计算结果和图表")
