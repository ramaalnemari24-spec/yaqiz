# يقظ | YAQIZ — Fleet Safety Control Center (Prototype)

Operator dashboard prototype for the YAQIZ truck safety system (DMS + TADS + GPS).
All data is **synthetic** and generated in Python.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files

| File | What it does |
|---|---|
| `simulation.py` | Fleet, routes, scripted night-shift scenario, **Central Event Manager** rules, risk score, event log, pre/post-accident window, 30-day history |
| `app.py` | Streamlit dashboard (live map, truck details, analytics, event log) |

## Demo scenario (night shift 01:00–04:00, 6 trucks)

| Time | Truck | What happens | Dashboard alert |
|---|---|---|---|
| 01:30 | TRK-02 | Driver uses phone | Driver Warning |
| 01:40 | TRK-03 | Repeated yawning, early fatigue | Driver Warning |
| 02:15 | TRK-03 | Long eye closures (PERCLOS > 20%) | Driver Warning (drowsy) |
| 02:50 | TRK-03 | Drowsy + strong vibration (lane drift) | Combined Risk Alert |
| 02:58 | TRK-03 | Collision on Riyadh–Dammam road (11.8 g) | Accident Alert + emergency notice |
| 03:17 | TRK-05 | Hard braking, tilt rising on Al-Hada descent | Vehicle Warning |
| 03:20 | TRK-05 | Rollover (tilt ≈ 88°) | Critical Accident Alert |

## Suggested 2-minute demo

1. Press **▶ تشغيل** — trucks move on the map, the feed fills.
2. Jump to **بداية الإرهاق (TRK-03)**, open **تفاصيل الشاحنة** — PERCLOS chart rising.
3. Jump to **اصطدام (TRK-03)** — red banner, ring-buffer chart shows the 10 minutes before the crash (fatigue → impact → speed 0).
4. Jump to **انقلاب (TRK-05)** — critical alert, tilt chart.
5. Open **تحليلات الأسطول** — fatigue peaks before dawn, driver ranking, hotspot map: the data-platform value.
