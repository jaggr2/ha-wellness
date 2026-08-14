# Wellness — Home Assistant health & meal tracking

Multi-user wellness tracking for Home Assistant:

- **Body metrics** — per-user body weight (kg) and waist (cm), manual logging with trend charts (long-term statistics) and append-only JSONL ledgers.
- **Smart-scale assignment** — shared scale readings are auto-assigned to a user when unambiguous (last weight within ±5 kg), otherwise admins are asked.
- **Meal photos** — one-tap camera capture from the Companion app, stored on your NAS with a JSONL meal log.
- **VLM meal analysis** *(phase 3)* — DeepSeek vision detects food & beverages, estimates amounts and kcal.

HACS-ready: `custom_components/wellness/` + camera card + example automations + dashboard.

> Not affiliated with Home Assistant.

## Status

Under active development.
