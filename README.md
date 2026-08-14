# Wellness — Home Assistant health & meal tracking

Multi-user wellness tracking for Home Assistant.

## Features

- **Body metrics** — per-participant **body weight** (kg) and **waist** (cm) number entities, mirrored to `state_class: measurement` sensors so Home Assistant records long-term statistics (trend charts).
- **JSONL ledgers** — a "Save body metrics" button (or the `wellness.save_body_metrics` service) appends to `body-metrics-<user>.jsonl` on your NAS mount, deduplicated against the last row.
- **Multi-user** — every participant is a Home Assistant account; each gets their own device, entities and ledgers.

### Roadmap
- **Smart-scale assignment** — shared scale readings auto-assigned to a user when unambiguous (within ±5 kg of their last reading), admins asked otherwise.
- **Meal photos** — one-tap camera capture from the Companion app into `food-photos/<user>/…` with a meal log.
- **VLM meal analysis** — Groq (llama-vision) detects food & beverages, estimates amounts and kcal.
- **Reminders** — per-user measurement schedule (weekday + time + interval).

## Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/jaggr2/ha-wellness`, category **Integration**.
2. Install **Wellness** → restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Wellness**.

### Manual
```bash
git clone https://github.com/jaggr2/ha-wellness.git
cp -r ha-wellness/custom_components/wellness <config>/custom_components/
```

## Configuration

During setup you provide:
- **Wellness data folder** — the mounted NAS path where ledgers/photos are stored (default `/mnt/data/supervisor/mounts/wellness`).
- **Participants** — the Home Assistant users taking part (one account per person).

Add/remove participants anytime via the entry's **Configure** dialog.

### Data layout
```
<mount>/wellness/
├── body-metrics-<user>.jsonl   {"ts","weight_kg","waist_cm","source"}
├── meal-log-<user>.jsonl       (phase 2)
└── food-photos/<user>/…        (phase 2)
```

## Services

- `wellness.save_body_metrics` — `{user: <slug>}` appends the participant's current weight/waist to their ledger.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## License

Apache-2.0. Not affiliated with Home Assistant.
