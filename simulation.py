"""
YAQIZ | يقظ — Simulation & Central Event Manager
-------------------------------------------------
This module produces SYNTHETIC data only. It mimics what the real system
would send to the dashboard:
  * DMS  (Raspberry Pi 5 + NoIR camera)  -> driver state
  * TADS (ESP32-S3 + ADXL375 + BMI088)    -> motion / accident state
  * GPS  (NEO-M8N)                       -> position + speed
  * Central Event Manager                -> unified alert per reading

No Streamlit here, so the logic can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

SEED = 7
SHIFT_START = datetime(2026, 11, 10, 1, 0)   # night shift 01:00
SHIFT_MINUTES = 180                          # until 04:00, one reading per minute

# ----------------------------------------------------------------------------
# Fleet (fictional drivers, approximate route geometry)
# ----------------------------------------------------------------------------
ROUTES = {
    "الرياض ← الدمام": [(24.71, 46.68), (24.95, 47.35), (25.32, 48.25), (25.75, 49.20), (26.30, 50.00)],
    "جدة ← مكة": [(21.54, 39.17), (21.49, 39.45), (21.42, 39.83)],
    "الطائف ← مكة (عقبة الهدا)": [(21.27, 40.42), (21.33, 40.33), (21.36, 40.28), (21.40, 40.05), (21.42, 39.83)],
    "الرياض ← بريدة": [(24.71, 46.68), (25.30, 45.90), (25.85, 44.90), (26.33, 43.97)],
    "الدمام ← الجبيل": [(26.43, 50.10), (26.70, 49.85), (27.00, 49.66)],
    "جدة ← المدينة": [(21.54, 39.17), (22.40, 39.10), (23.30, 39.25), (24.47, 39.61)],
}


@dataclass
class Truck:
    truck_id: str
    plate: str
    driver: str
    driver_id: str
    route: str
    cargo: str
    start_progress: float  # where on the route the truck is at 01:00 (0..1)
    cruise_kmh: int


FLEET = [
    Truck("TRK-01", "أ ب ج 1234", "سعد العتيبي", "DRV-101", "الرياض ← بريدة", "مواد غذائية", 0.10, 92),
    Truck("TRK-02", "ر س ط 5521", "خالد الحربي", "DRV-102", "جدة ← المدينة", "مواد بناء", 0.15, 88),
    Truck("TRK-03", "ك ل م 7788", "فهد القحطاني", "DRV-103", "الرياض ← الدمام", "حاويات", 0.05, 95),
    Truck("TRK-04", "ه و ي 3310", "ماجد الشهري", "DRV-104", "الدمام ← الجبيل", "كيماويات (مرخّصة)", 0.05, 80),
    Truck("TRK-05", "ن ع ف 9042", "عبدالله الثبيتي", "DRV-105", "الطائف ← مكة (عقبة الهدا)", "خضار وفواكه", 0.00, 45),
    Truck("TRK-06", "ص ق ب 6617", "تركي الغامدي", "DRV-106", "جدة ← مكة", "مياه معبأة", 0.00, 70),
]
FLEET_BY_ID = {t.truck_id: t for t in FLEET}

# ----------------------------------------------------------------------------
# Central Event Manager (the integration logic from section 7 of the proposal)
# ----------------------------------------------------------------------------
ALERT_LEVELS = {
    "Normal": 0,
    "Driver Warning": 1,
    "Vehicle Warning": 1,
    "Combined Risk Alert": 2,
    "Accident Alert": 3,
    "Critical Accident Alert": 4,
}


def central_event_manager(driver_status: str, accident_status: str,
                          accident_type: str, severity: str) -> str:
    """Unify DMS + TADS outputs into one alert, by the rules in the proposal."""
    if accident_status == "Detected":
        return "Critical Accident Alert" if accident_type == "Rollover" else "Accident Alert"
    if accident_status == "Suspected" and driver_status != "Normal":
        return "Combined Risk Alert"
    if accident_status == "Suspected":
        return "Vehicle Warning"          # abnormal motion, driver looks fine
    if driver_status != "Normal":
        return "Driver Warning"
    return "Normal"


def risk_score(driver_status: str, perclos: float, phone: bool, yawns_15min: int,
               accident_status: str, hours_driving: float) -> int:
    """0-100 driver/truck risk index shown on the dashboard."""
    score = 8
    score += min(perclos, 0.6) * 90          # % eye closure is the main fatigue signal
    score += 22 if phone else 0
    score += min(yawns_15min, 4) * 4
    score += max(0.0, hours_driving - 4) * 3  # long continuous driving
    score += {"Normal": 0, "Suspected": 18, "Detected": 40}[accident_status]
    if driver_status == "Drowsy":
        score = max(score, 60)
    if accident_status == "Detected":
        score = max(score, 95)
    return int(np.clip(round(score), 0, 100))


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------
def _haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(np.radians, (*a, *b))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))


def route_length_km(route: str) -> float:
    pts = ROUTES[route]
    return float(sum(_haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1)))


def point_on_route(route: str, progress: float):
    """Interpolate a (lat, lon) at progress 0..1 along the route polyline."""
    pts = ROUTES[route]
    progress = float(np.clip(progress, 0, 1))
    seg = [_haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    target = progress * sum(seg)
    for i, d in enumerate(seg):
        if target <= d or i == len(seg) - 1:
            f = 0 if d == 0 else min(target / d, 1)
            return (pts[i][0] + f * (pts[i + 1][0] - pts[i][0]),
                    pts[i][1] + f * (pts[i + 1][1] - pts[i][1]))
        target -= d
    return pts[-1]


# ----------------------------------------------------------------------------
# Scripted demo scenario (minute offsets from 01:00)
# ----------------------------------------------------------------------------
# TRK-03: fatigue builds up on the Riyadh–Dammam highway, ends in a collision
# TRK-05: brake/steering event on the Al-Hada descent -> rollover
# TRK-02: repeated phone use
SCENARIO_NOTES = [
    ("01:30", "TRK-02", "استخدام الجوال أثناء القيادة — تنبيه للسائق"),
    ("01:40", "TRK-03", "بداية علامات الإرهاق: تثاؤب متكرر"),
    ("02:15", "TRK-03", "إغلاق العينين لفترات طويلة — نعاس"),
    ("02:50", "TRK-03", "نعاس + اهتزاز قوي (خروج عن المسار) — خطر مركّب"),
    ("02:58", "TRK-03", "اصطدام مؤكد — إرسال تنبيه طوارئ مع الموقع"),
    ("03:20", "TRK-05", "انقلاب في عقبة الهدا — تنبيه حرج"),
]

COLLISION_MIN = 118   # 02:58
ROLLOVER_MIN = 140    # 03:20


def _driver_profile(truck_id: str, m: int, rng):
    """Return (driver_status, perclos, yawn, phone, head_pose) for minute m."""
    perclos = abs(rng.normal(0.04, 0.015))
    yawn = rng.random() < 0.01
    phone = False
    head = "Forward"

    if truck_id == "TRK-02" and (30 <= m <= 33 or 85 <= m <= 87 or 150 <= m <= 151):
        phone, head = True, "Down"

    if truck_id == "TRK-03":
        if 40 <= m < 75:          # early fatigue
            perclos = abs(rng.normal(0.10, 0.03))
            yawn = rng.random() < 0.35
        elif 75 <= m < COLLISION_MIN:   # drowsy
            perclos = abs(rng.normal(0.28 + (m - 75) * 0.004, 0.04))
            yawn = rng.random() < 0.45
            head = "Nodding" if rng.random() < 0.4 else "Forward"
        elif m >= COLLISION_MIN:
            perclos = abs(rng.normal(0.05, 0.02))

    if phone:
        status = "Distracted"
    elif perclos >= 0.20:
        status = "Drowsy"
    elif perclos >= 0.10 and yawn:
        status = "Fatigued"
    else:
        status = "Normal"
    return status, round(float(perclos), 3), yawn, phone, head


def _motion_profile(truck_id: str, m: int, rng, cruise: int):
    """Return (accident_status, type, severity, accel_g, tilt_deg, gyro_dps, speed)."""
    accel = abs(rng.normal(1.0, 0.12))
    tilt = rng.normal(0, 1.5)
    gyro = abs(rng.normal(2, 1))
    speed = max(0, int(rng.normal(cruise, 4)))
    status, kind, sev = "Normal", "-", "-"

    if truck_id == "TRK-03":
        if COLLISION_MIN - 8 <= m < COLLISION_MIN - 5:       # rumble strip / lane drift
            accel, gyro = abs(rng.normal(3.4, 0.4)), abs(rng.normal(18, 4))
            status, kind, sev = "Suspected", "Collision", "Medium"
        elif m == COLLISION_MIN:
            accel, gyro, speed = 11.8, 64.0, 0
            status, kind, sev = "Detected", "Collision", "High"
        elif m > COLLISION_MIN:
            accel, gyro, speed = abs(rng.normal(1.0, 0.05)), abs(rng.normal(0.5, 0.2)), 0
            status, kind, sev = "Detected", "Collision", "High"

    if truck_id == "TRK-05":
        if ROLLOVER_MIN - 3 <= m < ROLLOVER_MIN:            # hard braking on descent
            accel, tilt, gyro = abs(rng.normal(2.6, 0.3)), rng.normal(14 + (m - ROLLOVER_MIN + 3) * 9, 2), 25
            status, kind, sev = "Suspected", "Rollover", "Medium"
        elif m >= ROLLOVER_MIN:
            accel = 7.5 if m == ROLLOVER_MIN else abs(rng.normal(1.0, 0.05))
            tilt, gyro, speed = rng.normal(88, 1.0), (95 if m == ROLLOVER_MIN else 0.5), 0
            status, kind, sev = "Detected", "Rollover", "High"

    return status, kind, sev, round(float(accel), 2), round(float(tilt), 1), round(float(gyro), 1), speed


def simulate_shift(seed: int = SEED) -> pd.DataFrame:
    """One reading per truck per minute for the 3-hour night shift."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in FLEET:
        length = route_length_km(t.route)
        progress = t.start_progress
        yawn_hist: list[int] = []
        stopped_at = None
        for m in range(SHIFT_MINUTES):
            ts = SHIFT_START + timedelta(minutes=m)
            drv, perclos, yawn, phone, head = _driver_profile(t.truck_id, m, rng)
            acc, kind, sev, accel, tilt, gyro, speed = _motion_profile(t.truck_id, m, rng, t.cruise_kmh)

            if speed > 0 and stopped_at is None:
                progress = min(1.0, progress + speed / 60 / length)
                if progress >= 1.0:     # loop the route so trucks keep moving in the demo
                    progress = 0.0
            if acc == "Detected" and stopped_at is None:
                stopped_at = progress
            lat, lon = point_on_route(t.route, stopped_at if stopped_at is not None else progress)

            yawn_hist = (yawn_hist + [int(yawn)])[-15:]
            alert = central_event_manager(drv, acc, kind, sev)
            hours = 2.5 + m / 60  # drivers already 2.5 h into their trip at 01:00
            score = risk_score(drv, perclos, phone, sum(yawn_hist), acc, hours)

            emergency = "-"
            if acc == "Detected":
                first = (t.truck_id == "TRK-03" and m == COLLISION_MIN) or \
                        (t.truck_id == "TRK-05" and m == ROLLOVER_MIN)
                emergency = "Sent" if first else "Acknowledged"

            rows.append({
                "time": ts, "minute": m, "truck_id": t.truck_id, "plate": t.plate,
                "driver": t.driver, "driver_id": t.driver_id, "route": t.route, "cargo": t.cargo,
                "lat": round(lat, 5), "lon": round(lon, 5), "speed_kmh": speed,
                "driver_status": drv, "perclos": perclos, "yawning": yawn, "phone": phone,
                "head_pose": head, "accident_status": acc, "accident_type": kind,
                "severity": sev, "accel_g": accel, "tilt_deg": tilt, "gyro_dps": gyro,
                "risk_score": score, "alert": alert, "alert_level": ALERT_LEVELS[alert],
                "emergency": emergency, "hours_driving": round(hours, 2),
            })
    return pd.DataFrame(rows)


def event_log(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse minute readings into events: a new event starts when a truck's alert changes."""
    d = df.sort_values(["truck_id", "time"]).copy()
    d["changed"] = d.groupby("truck_id")["alert"].transform(lambda s: s.ne(s.shift()))
    ev = d[d["changed"] & (d["alert"] != "Normal")]
    return ev.drop(columns="changed").sort_values("time", ascending=False).reset_index(drop=True)


def accident_window(df: pd.DataFrame, truck_id: str, before: int = 10, after: int = 5) -> pd.DataFrame:
    """Readings before/after the first detected accident (the ring-buffer record, objective 8)."""
    d = df[df["truck_id"] == truck_id]
    hit = d[d["accident_status"] == "Detected"]
    if hit.empty:
        return d.iloc[0:0]
    m0 = int(hit["minute"].iloc[0])
    w = d[(d["minute"] >= m0 - before) & (d["minute"] <= m0 + after)].copy()
    w["t_rel"] = w["minute"] - m0
    return w


# ----------------------------------------------------------------------------
# 30-day history for the analytics tab (data-platform value, Track 05)
# ----------------------------------------------------------------------------
EVENT_TYPES = ["Drowsiness", "Phone Use", "Distraction", "Harsh Braking", "Suspected Impact", "Collision", "Rollover"]


def simulate_history(days: int = 30, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    # fatigue peaks before dawn and after lunch
    hour_w = np.array([5, 6, 8, 9, 8, 6, 3, 2, 2, 2, 2, 2, 3, 4, 5, 4, 3, 2, 2, 2, 3, 3, 4, 4], float)
    hour_w /= hour_w.sum()
    driver_risk = {"DRV-101": 0.8, "DRV-102": 1.6, "DRV-103": 2.2, "DRV-104": 0.6, "DRV-105": 1.1, "DRV-106": 0.9}
    type_p = np.array([0.34, 0.22, 0.16, 0.18, 0.07, 0.02, 0.01])
    end = SHIFT_START.replace(hour=0)
    rows = []
    for t in FLEET:
        n = rng.poisson(14 * driver_risk[t.driver_id])
        for _ in range(n):
            day = int(rng.integers(1, days + 1))
            hour = int(rng.choice(24, p=hour_w))
            ts = end - timedelta(days=day) + timedelta(hours=hour, minutes=int(rng.integers(0, 60)))
            kind = str(rng.choice(EVENT_TYPES, p=type_p))
            lat, lon = point_on_route(t.route, float(rng.beta(2, 2)))
            rows.append({
                "time": ts, "date": ts.date(), "hour": hour, "truck_id": t.truck_id,
                "driver": t.driver, "driver_id": t.driver_id, "route": t.route,
                "event": kind, "lat": lat + rng.normal(0, 0.01), "lon": lon + rng.normal(0, 0.01),
            })
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
