# Wellness — Home Assistant health & meal tracking

Multi-user wellness tracking for Home Assistant.

## Features

- **Body metrics** — per-participant **body weight** (kg) and **waist** (cm) number entities, mirrored to `state_class: measurement` sensors so Home Assistant records long-term statistics (trend charts).
- **JSONL ledgers** — a "Save body metrics" button (or the `wellness.save_body_metrics` service) appends to `body-metrics-<user>.jsonl` on your NAS mount, deduplicated against the last row.
- **Meal photos** — an authenticated `POST /api/wellness/photo` endpoint + a camera card. The participant is resolved from the logged-in HA account, so each person just opens their own app and taps. Photos land in `food-photos/<user>/YYYY/MM/DD/…` with a `meal-log-<user>.jsonl` entry.
- **Smart-scale assignment** — connect your shared weight sensor(s) in the options. Readings are auto-assigned to a participant when unambiguous (last weight within **±5 kg** and ≤ **60 days** old); otherwise a pending reading is created, the `wellness_pending_weight` event fires (for admin notification), and `sensor.wellness_pending` + the **assign card** let you resolve it explicitly. Deduplicated against repeated pushes. Sensor values are normalized to **kg** (g / lb / oz / st supported).
- **Reminders** — per-participant schedule (weekday + time + every-N-days, default Sunday 20:00 weekly); the integration fires `wellness_measurement_reminder` for you to notify via your own automation.
- **VLM meal analysis (Groq)** — `wellness.analyze_meals` runs Groq `llama-vision` on new meal photos and stores structured analysis (`food`, `beverages`, amounts, `estimated_kcal_total` + per item) in `meal-analysis-<user>.jsonl`, with per-participant **Today kcal** and **Last meal** sensors.
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
2. In **Configure** → paste the key (model default `llama-3.2-11b-vision-preview`).
3. Run `wellness.analyze_meals {user: roger}` (or an automation on the `wellness_meal_logged` event) — unanalyzed meal photos are sent to Groq and the result stored.

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
