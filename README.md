# Wellness — Home Assistant health & meal tracking

Multi-user wellness tracking for Home Assistant.

## Features

- **Body metrics** — per-participant **body weight** (kg) and **waist** (cm) number entities, mirrored to `state_class: measurement` sensors so Home Assistant records long-term statistics (trend charts).
- **JSONL ledgers** — a "Save body metrics" button (or the `wellness.save_body_metrics` service) appends to `body-metrics-<user>.jsonl` on your NAS mount, deduplicated against the last row.
- **Meal photos** — an authenticated `POST /api/wellness/photo` endpoint + a camera card. The participant is resolved from the logged-in HA account, so each person just opens their own app and taps. Photos land in `food-photos/<user>/YYYY/MM/DD/…` with a `meal-log-<user>.jsonl` entry.
- **Smart-scale assignment** — connect your shared weight sensor(s) in the options. Readings are auto-assigned to a participant when unambiguous (last weight within **±5 kg** and ≤ **60 days** old); otherwise a pending reading is created, the `wellness_pending_weight` event fires (for admin notification), and `sensor.wellness_pending` + the **assign card** let you resolve it explicitly. Deduplicated against repeated pushes. Sensor values are normalized to **kg** (g / lb / oz / st supported).
- **Reminders** — per-participant schedule (weekday + time + every-N-days, default Sunday 20:00 weekly); the integration fires `wellness_measurement_reminder` for you to notify via your own automation.
- **VLM meal analysis (Groq)** — new meal photos are **analyzed automatically** (no manual step): after a photo is uploaded, the integration runs Groq vision (`qwen/qwen3.6-27b`) on it and stores structured analysis (`food`, `beverages`, amounts, `estimated_kcal_total` + per item) in `meal-analysis-<user>.jsonl`. A per-user **Meal analysis status** sensor (`analyzing`/`done`/`error`, with `kcal`/`food`/`photo` attributes) powers the capture card's "Analyzing… → result" feedback, and the **Today kcal** / **Last meal** sensors update. You can also run `wellness.analyze_meals` manually.
- **Meal log & delete** — the **meal log card** lists recent meals (photo, time, detected food, kcal) from the authenticated `GET /api/wellness/meals` endpoint and lets you delete wrong entries (`POST /api/wellness/meal/delete` or the `wellness.delete_meal` service), removing the photo, meal-log and meal-analysis rows.
- **Daily kcal target & progress** — each participant has a **daily kcal target** (set in Configure → edit participant). The **Kcal remaining** sensor shows what's left today (with `target_kcal`/`consumed_kcal`/`percent_consumed` attributes) so you always know where you stand.
- **Eating regularity** — the **Meals today** sensor tracks how often you've eaten (count, today's meal times, min/avg/last gap in minutes) and flags `too_frequent` when consecutive meals are closer than 2 hours (snacking).
- **Multi-user** — every participant is a Home Assistant account; each gets their own device, entities and ledgers.

## Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/jaggr2/ha-wellness`, category **Integration**.
2. Install **Wellness** → restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Wellness**.

### Cards (for meal capture + pending assignment)
Copy the `www/` folders to `<config>/www/`, then register as Lovelace resources:
- `/local/wellness-capture-card/wellness-capture-card.js`
- `/local/wellness-assign-card/wellness-assign-card.js`
- `/local/wellness-meal-log-card/wellness-meal-log-card.js`

### Manual
```bash
git clone https://github.com/jaggr2/ha-wellness.git
cp -r ha-wellness/custom_components/wellness <config>/custom_components/
```

## Configuration

During setup you provide:
- **Wellness data folder** — pick one of your configured NAS mounts (or type a path). Default `wellness → /share/wellness`.
- **Participants** — the Home Assistant users taking part (one account per person).

In **Configure** you can: add/remove participants, edit a participant's name + measurement schedule, select **shared weight sensors** (the smart scale(s)) that feed auto-assignment, and set the **Groq API key + vision model** for meal analysis.

### Meal analysis (Groq)
1. Get a free key at https://console.groq.com/keys (Groq offers a free tier).
2. In **Configure** → paste the key (model default `qwen/qwen3.6-27b`).
3. Meal photos are analyzed automatically after upload. The capture card shows "Analyzing…" then the kcal/food result; the `Meal analysis status` sensor and `Today kcal` / `Last meal` sensors update too. Or run `wellness.analyze_meals {user: roger}` (or an automation on the `wellness_meal_logged` event) to (re)process unanalyzed photos.

### Data layout
```
<mount>/wellness/
├── body-metrics-<user>.jsonl   {"ts","weight_kg","waist_cm","source","assigned_by","sensor_id"}
├── meal-log-<user>.jsonl       {"ts","photo","source"}
├── meal-analysis-<user>.jsonl  {"ts","photo","food","beverages","estimated_kcal_total","…"}
└── food-photos/<user>/YYYY/MM/DD/*.jpg
```

## Events & services

Events (fire on the bus, for your automations):
- `wellness_measurement_reminder` — `{user, name, interval_days}` (per-participant schedule)
- `wellness_pending_weight` — `{reading_id, weight_kg, sensor_id, candidates}` (ambiguous scale reading)
- `wellness_weight_assigned` — `{user, weight_kg, assigned_by}`

Services:
- `wellness.save_body_metrics` — `{user: <slug>}`
- `wellness.assign_weight` — `{reading_id, user: <slug>}`
- `wellness.dismiss_weight` — `{reading_id}`
- `wellness.analyze_meals` — `{user: <slug>, limit?: <n>}` (Groq vision)

Example automations (reminder + pending-scale notification) and a dashboard are in `example-automations/` and `example-dashboard.yaml`.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## License

Apache-2.0. Not affiliated with Home Assistant.
