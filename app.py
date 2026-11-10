"""
YAQIZ | يقظ — Fleet Safety Control Center (prototype)
Run:  streamlit run app.py
All data is synthetic (see simulation.py).
"""

import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

import simulation as sim

st.set_page_config(page_title="يقظ | YAQIZ", page_icon="🛡️", layout="wide")

# ----------------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------------
BG, CARD, LINE, TEXT, MUTED = "#0a1220", "#121e31", "#22344d", "#e8eef6", "#8fa3bb"
OK, WARN, HIGH, CRIT = "#2bb59a", "#e3a73b", "#ef6f3c", "#e5484d"
ALERT_COLOR = {
    "Normal": OK, "Driver Warning": WARN, "Vehicle Warning": WARN,
    "Combined Risk Alert": HIGH, "Accident Alert": CRIT, "Critical Accident Alert": CRIT,
}
ALERT_AR = {
    "Normal": "طبيعي", "Driver Warning": "تحذير سائق", "Vehicle Warning": "تحذير مركبة",
    "Combined Risk Alert": "خطر مركّب", "Accident Alert": "تنبيه حادث",
    "Critical Accident Alert": "حادث حرج",
}
DRIVER_AR = {"Normal": "طبيعي", "Fatigued": "إرهاق", "Drowsy": "نعاس", "Distracted": "تشتت"}
ACC_AR = {"Normal": "طبيعي", "Suspected": "اشتباه", "Detected": "مؤكد"}
TYPE_AR = {"-": "—", "Collision": "اصطدام", "Rollover": "انقلاب"}
HEAD_AR = {"Forward": "للأمام", "Down": "للأسفل (نحو الجوال)", "Nodding": "إيماء (نعاس)"}
SEV_AR = {"-": "—", "Low": "منخفضة", "Medium": "متوسطة", "High": "عالية"}
EVENT_AR = {
    "Drowsiness": "نعاس", "Phone Use": "استخدام الجوال", "Distraction": "تشتت",
    "Harsh Braking": "فرملة حادة", "Suspected Impact": "اشتباه اصطدام",
    "Collision": "اصطدام", "Rollover": "انقلاب",
}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;700&display=swap');
html, body, .stApp, [class*="css"] {{ font-family: 'IBM Plex Sans Arabic', sans-serif; }}
.stApp {{ background: {BG}; color: {TEXT}; }}
.main .block-container {{ direction: rtl; padding-top: 1.2rem; }}
[data-testid="stSidebar"] {{ background: #0e192b; direction: rtl; }}
h1, h2, h3, h4, p, label, .stMarkdown {{ text-align: right; }}
[data-testid="stTabs"] button p {{ font-size: 15px; font-weight: 600; }}

.topbar {{ display:flex; justify-content:space-between; align-items:center;
          border-bottom:1px solid {LINE}; padding-bottom:12px; margin-bottom:14px; }}
.brand {{ font-size:28px; font-weight:700; color:{TEXT}; }}
.brand span {{ color:{OK}; }}
.clock {{ font-size:15px; color:{MUTED}; text-align:left; direction:ltr; }}
.clock b {{ color:{TEXT}; font-size:22px; }}

.kpi {{ background:{CARD}; border:1px solid {LINE}; border-radius:12px; padding:14px 16px; }}
.kpi .v {{ font-size:28px; font-weight:700; line-height:1.1; }}
.kpi .l {{ font-size:13px; color:{MUTED}; }}

.feed {{ background:{CARD}; border:1px solid {LINE}; border-radius:12px; padding:6px 12px;
         max-height:470px; overflow-y:auto; }}
.item {{ border-bottom:1px solid {LINE}; padding:9px 0; }}
.item:last-child {{ border-bottom:none; }}
.item .t {{ font-size:12px; color:{MUTED}; direction:ltr; text-align:right; }}
.pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px;
         font-weight:600; color:#0a1220; }}
.truckcard {{ background:{CARD}; border:1px solid {LINE}; border-radius:12px; padding:12px 14px; }}
.truckcard .row {{ display:flex; justify-content:space-between; font-size:14px; padding:3px 0; }}
.truckcard .row span:first-child {{ color:{MUTED}; }}
.banner {{ border-radius:12px; padding:12px 16px; font-weight:600; margin-bottom:12px; }}
</style>
""", unsafe_allow_html=True)


def show_chart(fig):
    """plotly_chart full width on old and new Streamlit versions."""
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def style_fig(fig, height=300):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family="IBM Plex Sans Arabic"),
        legend=dict(orientation="h", y=-0.2), title_x=1, title_xanchor="right",
    )
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def pill(alert):
    return f'<span class="pill" style="background:{ALERT_COLOR[alert]}">{ALERT_AR[alert]}</span>'


def hex_rgb(h, a=230):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [a]


# ----------------------------------------------------------------------------
# Data (cached: generated once per session)
# ----------------------------------------------------------------------------
@st.cache_data
def load():
    shift = sim.simulate_shift()
    return shift, sim.event_log(shift), sim.simulate_history()


SHIFT, EVENTS, HISTORY = load()
MAX_MIN = sim.SHIFT_MINUTES - 1

if "minute" not in st.session_state:
    st.session_state.minute = 25
if "playing" not in st.session_state:
    st.session_state.playing = False
if "speed" not in st.session_state:
    st.session_state.speed = 2


def goto(m):
    st.session_state.minute, st.session_state.playing = m, False


def toggle_play():
    if st.session_state.minute >= MAX_MIN:
        st.session_state.minute = 0
    st.session_state.playing = not st.session_state.playing


# advance the clock BEFORE the slider widget is drawn (Streamlit forbids editing it afterwards)
if st.session_state.playing:
    st.session_state.minute = min(MAX_MIN, st.session_state.minute + st.session_state.speed)
    if st.session_state.minute >= MAX_MIN:
        st.session_state.playing = False

# ----------------------------------------------------------------------------
# Sidebar: simulation controls
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🛡️ يقظ | YAQIZ")
    st.caption("مركز التحكم بسلامة أسطول الشاحنات — نموذج أولي")
    st.divider()
    st.markdown("**محاكاة الوردية الليلية (01:00 – 04:00)**")

    c1, c2 = st.columns(2)
    c1.button("⏸ إيقاف" if st.session_state.playing else "▶ تشغيل", type="primary",
              on_click=toggle_play)
    c2.button("↺ من البداية", on_click=goto, args=(0,))

    st.select_slider("سرعة العرض (دقيقة/ثانية)", options=[1, 2, 5, 10], key="speed")
    st.slider("الوقت", 0, MAX_MIN, key="minute",
              format="%d د", help="حرّكي المؤشر للانتقال لأي لحظة في الوردية")

    st.divider()
    st.markdown("**انتقال سريع للأحداث**")
    for label, m in [("استخدام الجوال (TRK-02)", 30), ("بداية الإرهاق (TRK-03)", 42),
                     ("خطر مركّب (TRK-03)", 111), ("اصطدام (TRK-03)", 118),
                     ("انقلاب (TRK-05)", 140)]:
        st.button(label, key=f"jump{m}", on_click=goto, args=(m,))

    st.divider()
    st.caption("جميع البيانات وهمية لأغراض العرض، والمسارات تقريبية. "
               "لا توجد أجهزة أو خدمات طوارئ متصلة.")

M = st.session_state.minute
now = sim.SHIFT_START + pd.Timedelta(minutes=M)
upto = SHIFT[SHIFT["minute"] <= M]
latest = upto[upto["minute"] == M].copy()
events_now = EVENTS[EVENTS["minute"] <= M]

# ----------------------------------------------------------------------------
# Header + KPIs
# ----------------------------------------------------------------------------
st.markdown(f"""
<div class="topbar">
  <div class="brand">يقظ <span>|</span> مركز التحكم بسلامة الأسطول</div>
  <div class="clock">{now:%d/%m/%Y} &nbsp; <b>{now:%H:%M}</b> &nbsp; ● LIVE (SIM)</div>
</div>""", unsafe_allow_html=True)

active_acc = latest[latest["accident_status"] == "Detected"]
if not active_acc.empty:
    r = active_acc.sort_values("alert_level").iloc[-1]
    st.markdown(
        f'<div class="banner" style="background:{CRIT}22;border:1px solid {CRIT};">'
        f'🚨 {ALERT_AR[r.alert]} — {r.truck_id} ({r.driver}) — {TYPE_AR[r.accident_type]} على طريق {r.route} '
        f'— الموقع: {r.lat:.4f}, {r.lon:.4f} — تم إرسال الإشعار للجهات المختصة</div>',
        unsafe_allow_html=True)

kpis = [
    (len(sim.FLEET), "شاحنات تحت المراقبة", TEXT),
    (int((latest["speed_kmh"] > 0).sum()), "في الطريق الآن", OK),
    (int((latest["alert_level"].between(1, 2)).sum()), "تحذيرات نشطة", WARN),
    (int((latest["alert_level"] >= 3).sum()), "حوادث نشطة", CRIT),
    (len(events_now), "أحداث منذ بداية الوردية", TEXT),
    (f"{latest['risk_score'].mean():.0f}", "متوسط مؤشر الخطورة", TEXT),
]
for col, (v, l, c) in zip(st.columns(6), kpis):
    col.markdown(f'<div class="kpi"><div class="v" style="color:{c}">{v}</div>'
                 f'<div class="l">{l}</div></div>', unsafe_allow_html=True)

st.write("")
tab_live, tab_truck, tab_analytics, tab_log = st.tabs(
    ["🗺️ المراقبة الحية", "🚛 تفاصيل الشاحنة", "📊 تحليلات الأسطول (30 يوم)", "📋 سجل الأحداث"])

# ----------------------------------------------------------------------------
# Tab 1: live map + feed + fleet table
# ----------------------------------------------------------------------------
with tab_live:
    left, right = st.columns([2.2, 1])
    with left:
        paths = pd.DataFrame([{"route": k, "path": [[lon, lat] for lat, lon in v]}
                              for k, v in sim.ROUTES.items()])
        latest["color"] = latest["alert"].map(lambda a: hex_rgb(ALERT_COLOR[a]))
        latest["radius"] = latest["alert_level"].map(lambda x: 3500 + x * 2500)
        latest["status_ar"] = latest["alert"].map(ALERT_AR)
        deck = pdk.Deck(
            layers=[
                pdk.Layer("PathLayer", paths, get_path="path", get_color=[120, 150, 185, 110],
                          width_min_pixels=2),
                pdk.Layer("ScatterplotLayer", latest, get_position="[lon, lat]",
                          get_fill_color="color", get_radius="radius", radius_min_pixels=7,
                          radius_max_pixels=30, pickable=True, stroked=True,
                          get_line_color=[255, 255, 255, 200], line_width_min_pixels=1),
                pdk.Layer("TextLayer", latest, get_position="[lon, lat]", get_text="truck_id",
                          get_size=12, get_color=[232, 238, 246], get_pixel_offset=[0, -22]),
            ],
            initial_view_state=pdk.ViewState(latitude=23.6, longitude=44.6, zoom=4.6),
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            tooltip={"text": "{truck_id} — {driver}\n{route}\nالحالة: {status_ar}\n"
                             "السرعة: {speed_kmh} كم/س\nالخطورة: {risk_score}"},
        )
        st.pydeck_chart(deck, height=470)

    with right:
        st.markdown("#### آخر التنبيهات")
        items = []
        for _, e in events_now.head(14).iterrows():
            items.append(
                f'<div class="item">{pill(e.alert)} &nbsp;<b>{e.truck_id}</b> — {e.driver}'
                f'<div style="font-size:13px;color:{MUTED}">سائق: {DRIVER_AR[e.driver_status]} · '
                f'مركبة: {ACC_AR[e.accident_status]} · خطورة {e.risk_score}</div>'
                f'<div class="t">{e.time:%H:%M}</div></div>')
        st.markdown(f'<div class="feed">{"".join(items) or "<p>لا توجد تنبيهات حتى الآن</p>"}</div>',
                    unsafe_allow_html=True)

    st.markdown("#### حالة الأسطول الآن")
    table = latest.sort_values("alert_level", ascending=False)[[
        "truck_id", "driver", "route", "speed_kmh", "driver_status", "accident_status",
        "risk_score", "alert"]].copy()
    table["driver_status"] = table["driver_status"].map(DRIVER_AR)
    table["accident_status"] = table["accident_status"].map(ACC_AR)
    table["alert"] = table["alert"].map(ALERT_AR)
    table.columns = ["الشاحنة", "السائق", "المسار", "السرعة (كم/س)", "حالة السائق",
                     "حالة المركبة", "مؤشر الخطورة", "التنبيه"]
    st.dataframe(
        table, hide_index=True,
        column_config={"مؤشر الخطورة": st.column_config.ProgressColumn(
            "مؤشر الخطورة", min_value=0, max_value=100, format="%d")},
    )

# ----------------------------------------------------------------------------
# Tab 2: single truck — DMS + TADS + sensors + pre/post accident window
# ----------------------------------------------------------------------------
with tab_truck:
    if "tid" not in st.session_state:
        st.session_state.tid = "TRK-03"
    tid = st.selectbox("اختاري الشاحنة", [t.truck_id for t in sim.FLEET], key="tid",
                       format_func=lambda x: f"{x} — {sim.FLEET_BY_ID[x].driver}")
    hist = upto[upto["truck_id"] == tid]
    s = hist.iloc[-1]
    truck = sim.FLEET_BY_ID[tid]

    c1, c2, c3 = st.columns([1, 1, 1.1])
    with c1:
        st.markdown("##### 👤 مراقبة السائق (DMS)")
        st.markdown(f"""<div class="truckcard">
          <div class="row"><span>السائق</span><span>{truck.driver} ({truck.driver_id})</span></div>
          <div class="row"><span>الحالة</span><span>{DRIVER_AR[s.driver_status]}</span></div>
          <div class="row"><span>نسبة إغلاق العين PERCLOS</span><span>{s.perclos:.0%}</span></div>
          <div class="row"><span>تثاؤب (آخر 15 د)</span><span>{int(hist.tail(15)['yawning'].sum())}</span></div>
          <div class="row"><span>استخدام الجوال</span><span>{"نعم ⚠️" if s.phone else "لا"}</span></div>
          <div class="row"><span>وضعية الرأس</span><span>{HEAD_AR[s.head_pose]}</span></div>
          <div class="row"><span>ساعات القيادة المتواصلة</span><span>{s.hours_driving:.1f}</span></div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("##### 🚛 اكتشاف الحوادث (TADS)")
        st.markdown(f"""<div class="truckcard">
          <div class="row"><span>اللوحة</span><span>{truck.plate}</span></div>
          <div class="row"><span>الحمولة</span><span>{truck.cargo}</span></div>
          <div class="row"><span>حالة الحادث</span><span>{ACC_AR[s.accident_status]}</span></div>
          <div class="row"><span>النوع</span><span>{TYPE_AR[s.accident_type]}</span></div>
          <div class="row"><span>الشدة</span><span>{SEV_AR[s.severity]}</span></div>
          <div class="row"><span>السرعة (GPS)</span><span>{s.speed_kmh} كم/س</span></div>
          <div class="row"><span>إشعار الطوارئ</span><span>{s.emergency}</span></div>
        </div>""", unsafe_allow_html=True)
    with c3:
        score = int(s.risk_score)
        g = go.Figure(go.Indicator(
            mode="gauge+number", value=score, title={"text": "مؤشر الخطورة"},
            gauge={"axis": {"range": [0, 100]},
                   "bar": {"color": OK if score < 40 else WARN if score < 70 else CRIT},
                   "bgcolor": CARD, "borderwidth": 0,
                   "steps": [{"range": [0, 40], "color": "#14302c"},
                             {"range": [40, 70], "color": "#3a3020"},
                             {"range": [70, 100], "color": "#3d1f24"}]}))
        show_chart(style_fig(g, 260))

    st.markdown("##### قراءات الحساسات — آخر 60 دقيقة")
    last = hist.tail(60)
    s1, s2 = st.columns(2)
    with s1:
        f = go.Figure()
        f.add_scatter(x=last["time"], y=last["accel_g"], name="التسارع (g) — ADXL375",
                      line=dict(color=CRIT, width=2))
        f.add_scatter(x=last["time"], y=last["gyro_dps"] / 10, name="السرعة الزاوية ÷10 — BMI088",
                      line=dict(color=WARN, width=1.5, dash="dot"))
        f.add_hline(y=8, line_dash="dash", line_color=MUTED, annotation_text="حد الاصطدام 8g")
        show_chart(style_fig(f.update_layout(title="الحركة والصدمات")))
    with s2:
        f = go.Figure()
        f.add_scatter(x=last["time"], y=last["perclos"] * 100, name="PERCLOS %",
                      line=dict(color=OK, width=2), fill="tozeroy")
        f.add_scatter(x=last["time"], y=last["tilt_deg"], name="الميلان (°)",
                      line=dict(color="#7aa7ff", width=1.5))
        f.add_hline(y=20, line_dash="dash", line_color=MUTED, annotation_text="حد النعاس 20%")
        show_chart(style_fig(f.update_layout(title="إرهاق السائق وميلان الشاحنة")))

    win = sim.accident_window(hist, tid)
    if not win.empty:
        st.markdown("##### 📼 سجل ما قبل وبعد الحادث (Ring Buffer)")
        st.caption("الجهاز يحتفظ دائمًا بآخر 10 دقائق، وعند اكتشاف الحادث يُحفظ السجل ويُرسل مع التنبيه.")
        f = go.Figure()
        f.add_bar(x=win["t_rel"], y=win["accel_g"], name="التسارع (g)",
                  marker_color=[CRIT if v == 0 else "#3b5574" for v in win["t_rel"]])
        f.add_scatter(x=win["t_rel"], y=win["speed_kmh"], name="السرعة (كم/س)", yaxis="y2",
                      line=dict(color=OK, width=2))
        f.add_scatter(x=win["t_rel"], y=win["perclos"] * 100, name="PERCLOS %", yaxis="y2",
                      line=dict(color=WARN, width=2, dash="dot"))
        f.update_layout(xaxis_title="دقائق نسبةً للحادث",
                        yaxis2=dict(overlaying="y", side="right", showgrid=False))
        show_chart(style_fig(f, 320))

# ----------------------------------------------------------------------------
# Tab 3: 30-day analytics (the data-platform side)
# ----------------------------------------------------------------------------
with tab_analytics:
    H = HISTORY.copy()
    H["event_ar"] = H["event"].map(EVENT_AR)
    a1, a2, a3, a4 = st.columns(4)
    fatigue = H[H["event"] == "Drowsiness"]
    night = fatigue["hour"].between(0, 5).mean() if len(fatigue) else 0
    for col, v, l in [
        (a1, len(H), "إجمالي الأحداث (30 يوم)"),
        (a2, f"{night:.0%}", "من حالات النعاس بين 12–6 فجرًا"),
        (a3, H.groupby("driver").size().idxmax(), "السائق الأعلى أحداثًا"),
        (a4, H.groupby("route").size().idxmax(), "المسار الأعلى أحداثًا"),
    ]:
        col.markdown(f'<div class="kpi"><div class="v" style="font-size:20px">{v}</div>'
                     f'<div class="l">{l}</div></div>', unsafe_allow_html=True)
    st.write("")

    r1, r2 = st.columns(2)
    with r1:
        by_hour = (H.groupby(["hour", "event_ar"]).size().reset_index(name="عدد"))
        f = px.bar(by_hour, x="hour", y="عدد", color="event_ar", title="الأحداث حسب ساعة اليوم",
                   labels={"hour": "الساعة", "event_ar": "النوع"},
                   color_discrete_sequence=px.colors.qualitative.Set2)
        show_chart(style_fig(f, 340))
    with r2:
        drv = (H.groupby(["driver", "event_ar"]).size().reset_index(name="عدد"))
        order = H.groupby("driver").size().sort_values().index.tolist()
        f = px.bar(drv, y="driver", x="عدد", color="event_ar", orientation="h",
                   title="ترتيب السائقين حسب الأحداث", category_orders={"driver": order},
                   labels={"driver": "", "event_ar": "النوع"},
                   color_discrete_sequence=px.colors.qualitative.Set2)
        show_chart(style_fig(f, 340))

    r3, r4 = st.columns([1.3, 1])
    with r3:
        st.markdown("##### خريطة النقاط الساخنة")
        heat = pdk.Deck(
            layers=[pdk.Layer("HeatmapLayer", H, get_position="[lon, lat]", radius_pixels=40,
                              intensity=1, threshold=0.05)],
            initial_view_state=pdk.ViewState(latitude=23.6, longitude=44.6, zoom=4.4),
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json")
        st.pydeck_chart(heat, height=360)
    with r4:
        daily = H.groupby("date").size().reset_index(name="عدد")
        f = px.area(daily, x="date", y="عدد", title="الأحداث اليومية",
                    labels={"date": ""}, color_discrete_sequence=[OK])
        show_chart(style_fig(f, 380))
    st.caption("بيانات تاريخية وهمية مولّدة للعرض — توضّح نوع التحليلات التي تتيحها المنصة "
               "لشركات النقل والجهات التنظيمية.")

# ----------------------------------------------------------------------------
# Tab 4: event log + export
# ----------------------------------------------------------------------------
with tab_log:
    log = events_now[["time", "truck_id", "driver", "route", "alert", "driver_status",
                      "accident_status", "accident_type", "severity", "speed_kmh",
                      "accel_g", "tilt_deg", "risk_score", "lat", "lon", "emergency"]].copy()
    log["alert"] = log["alert"].map(ALERT_AR)
    log["driver_status"] = log["driver_status"].map(DRIVER_AR)
    log["accident_status"] = log["accident_status"].map(ACC_AR)
    log["accident_type"] = log["accident_type"].map(TYPE_AR)
    log["severity"] = log["severity"].map(SEV_AR)
    log["time"] = log["time"].dt.strftime("%H:%M")
    log.columns = ["الوقت", "الشاحنة", "السائق", "المسار", "التنبيه", "حالة السائق",
                   "حالة المركبة", "نوع الحادث", "الشدة", "السرعة", "التسارع g",
                   "الميلان °", "الخطورة", "خط العرض", "خط الطول", "إشعار الطوارئ"]
    if log.empty:
        st.info("لا توجد أحداث مسجلة حتى هذه اللحظة.")
    else:
        st.dataframe(log, hide_index=True)
        st.download_button("⬇️ تنزيل السجل CSV", log.to_csv(index=False).encode("utf-8-sig"),
                           file_name="yaqiz_events.csv", mime="text/csv")

st.caption("YAQIZ | يقظ — نموذج أولي ببيانات وهمية، لا يرسل تنبيهات طوارئ فعلية.")

# ----------------------------------------------------------------------------
# Playback loop
# ----------------------------------------------------------------------------
if st.session_state.playing:
    time.sleep(1)
    st.rerun()
