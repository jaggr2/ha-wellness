# Wellness — Project Status & Handoff

> Last updated: 2026-08-14 (evening session) · Author: Athena/Winston session with Roger
> Repo: `jaggr2/ha-wellness` (public, HACS-ready) · Latest release: **v0.5.0**

This file captures the current state, decisions, what has been built, and what
remains — so work can be resumed (or handed to another agent) without losing
context.

---

## 1. Goal

A multi-user health & meal tracker for Roger's home:

- **Body metrics**: weekly (default Sunday 20:00) weight + waist logging.
- **Meal photos**: one-tap camera capture per meal from the Home Assistant
  Android app.
- **Smart-scale assignment**: shared scale readings auto-assigned to a person
  (±5 kg rule), admins asked when ambiguous.
- **VLM analysis**: detect food & beverages, amounts, and kcal per meal (Groq).

---

## 2. Key decisions (locked)

| Topic | Decision |
|---|---|
| Multi-user model | Each **HA account = one participant**; integration resolves the user from the authenticated session; participants managed in the integration options. |
| Repo | **Public HACS repo** `jaggr2/ha-wellness`; integration + camera card + assign card + example automations + dashboard in the **same repo**. |
| Storage | **ZFS dataset + JSONL ledgers** on the NAS (append-only, matches backup-ledger pattern). |
| NAS mount | Dedicated **`nas/wellness`** dataset, shared via **Samba**, mounted in HA OS at **`/share/wellness`** (the supervisor `user_path`). |
| Ingest transport | **HA webhook-free**: authenticated `POST /api/wellness/photo` (multipart); card uploads directly; **no webhookd** (explicit user choice). |
| Photo capture UX | **Dashboard camera card** (Android); `<input type=file accept=image/*>` opens the phone camera; participant auto-resolved server-side. |
| Photo metadata | **Photo only** (no meal-type/notes) — VLM derives content later. |
| Scale assignment | Shared **weight sensors** (configured in options); auto-assign if exactly one participant's last weight is within **±5 kg** and **≤60 days** old; **0 or >1 candidates → ask**; **always explicit choice** (no pre-selection); dedup repeated pushes. |
| "Ask" UX | Admins notified (`wellness_pending_weight` event + example automation); **assign card** resolves via dropdown; services `wellness.assign_weight` / `dismiss_weight`. |
| Reminders | Per-participant **weekday + time + every-N-days** (default Sunday 20:00 / 7); integration fires `wellness_measurement_reminder`; notification is left to user automations. |
| VLM provider | **Groq** (`qwen/qwen3.6-27b`, OpenAI-compatible). DeepSeek hosted API was **verified text-only** (rejected `image_url`) so it can't do vision. *(2026-08-14 evening: `llama-3.2-11b-vision-preview` was decommissioned by Groq — migrated to the only current Groq vision model, `qwen/qwen3.6-27b`.)* |
| Units | Metric only (kg / cm). |
| Scope | `wellness` domain, `single_config_entry`, HACS installable. |

---

## 3. Infrastructure (Phase 0 — done)

**Rack server** (`192.168.11.11`, GitOps repo `jaggr2/home-control-server-config`, commit `74c152e`):
- ZFS dataset `nas/wellness` → `/mnt/nas/wellness`, owned `homelab:homelab`, `2775`.
- Samba `wellness` share added: quadlet `samba.container` volume `/mnt/nas/wellness:/wellness:z` + `SHARE4=wellness;/wellness;yes;no;no;homelab` in `~/config/quadlets.env` (gitignored; `.env.example` updated).
- Samba `homelab` password rotated (user-specified; lives only in `~/config/quadlets.env`, not git).
- Codified in `setup/02-zfs.sh` (dataset) and `setup/06-quadlet-deploy.sh` (ownership).

**Home Assistant OS**:
- SMB network storage **`wellness`** created via supervisor API — **active**; files visible/writable at **`/share/wellness`**.
- Note: core runs as **root**; the CIFS mount is `root:0755` so only root (core) writes — fine. (Server-side chmod does not change client view.)
- Known caveat: HA OS SMB mounts can fail to remount after a host reboot on some versions; **NFS is the fallback** if that bites.

**Storage layout**:
```
/share/wellness  (= /mnt/nas/wellness on the NAS)
├── body-metrics-<user>.jsonl   {"ts","weight_kg","waist_cm","source","assigned_by","sensor_id"}
├── meal-log-<user>.jsonl       {"ts","photo","source"}
├── meal-analysis-<user>.jsonl  {"ts","photo","food","beverages","estimated_kcal_total",…}
└── food-photos/<user>/YYYY/MM/DD/*.jpg
```

---

## 4. Integration — what's built (Phases 1–3)

### Domain `wellness`, latest **v0.3.0**

**Entities (per participant device)**
- `number.<user>_body_weight` (kg) · `number.<user>_waist` (cm) — `RestoreNumber`, persist across restarts.
- `sensor.<user>_body_weight_statistics` · `sensor.<user>_waist_statistics` — `state_class: measurement` → long-term statistics/charts.
- `button.<user>_save_metrics` → appends `body-metrics-<user>.jsonl` (`source: manual`, deduped).
- `sensor.<user>_today_kcal` · `sensor.<user>_last_meal` — from Groq analysis.
- Integration-level `sensor.wellness_pending` — count + `pending` attribute (unassigned scale readings).

**HTTP view (authenticated)**
- `POST /api/wellness/photo` — multipart `file` (jpeg/png/webp, ≤10 MB); resolves participant from `hass_user`; stores photo + meal-log entry; fires `wellness_meal_logged`.

**Smart-scale assignment**
- Options: shared weight sensors (entity selector).
- On sensor change → dedup → candidates (±5 kg, ≤60 days from each user's ledger) → auto-assign (`source: scale, assigned_by: auto`) or create pending + fire `wellness_pending_weight`.
- Pending persisted via `.storage` (`wellness.pending`); assign/dismiss services update it.

**Reminders**
- Per-participant schedule from options; `_seconds_until_next` computes next (weekday, time); fires `wellness_measurement_reminder`; reschedules every-N-days.

**Groq analysis**
- `wellness.analyze_meals {user, limit}` — reads unanalyzed meal-log photos, sends to Groq vision, stores structured analysis in `meal-analysis-<user>.jsonl`, updates today-kcal/last-meal sensors, fires `wellness_meal_analyzed`.

**Events**: `wellness_measurement_reminder` · `wellness_pending_weight` · `wellness_weight_assigned` · `wellness_meal_logged` · `wellness_meal_analyzed`

**Services**: `save_body_metrics` · `assign_weight` · `dismiss_weight` · `analyze_meals`

### Cards (`www/`, deployed to `/config/www/`)
- `wellness-capture-card/wellness-capture-card.js` — camera → resize ≤1600px → POST; shows thumbnail/status.
- `wellness-assign-card/wellness-assign-card.js` — lists pending readings; dropdown (candidates + all participants); Assign/Dismiss via services.

### Example files in repo
- `example-automations/measurement-reminder.yaml`
- `example-automations/scale-assign-notify.yaml`
- `example-dashboard.yaml`

### Tests
- `tests/`: ledger helpers, assignment engine, analyzer parsing — **16 passed**.

### Config / options flow
- Setup: mount path (selectable from supervisor mounts, default `wellness → /share/wellness`) + participants (multi-select HA users).
- Options: mount path · add/remove participants · edit participant (name, weekday, time, every-N-days) · shared weight sensors · Groq API key + model.

---

## 5. Current live state (verified 2026-08-14 evening)

- Config entry active on HA: mount `/share/wellness`, participants **`roger`** + **`derog_ha`**; entities registered (numbers, save buttons, statistics sensors, today-kcal/last-meal sensors, pending-assignments sensor).
- Photo endpoint registered (401 unauthenticated as designed).
- Core writes to the mount confirmed.
- `body-metrics-roger.jsonl` contains a real manual entry (118.0 kg) — ledger pipeline proven.
- Integration deployed to `/config/custom_components/wellness`; cards to `/config/www/`.
- **Smart scale configured**: `sensor.s24plus_weight` (Samsung Health via S24+ Companion) enabled + set as the shared weight sensor. Full flow live-verified:
  - auto-assign (117.8 kg → roger, ledger `source: scale, assigned_by: auto`),
  - ambiguous reading → `sensor.pending_weight_assignments` + `wellness_pending_weight` event,
  - `wellness.assign_weight` service → derog_ha ledger (`assigned_by: manual`).
- **Groq live-verified**: `wellness.analyze_meals {user: roger}` against `essen_test_image.jpg` → full structured analysis (steak, white/green asparagus, hollandaise, red wine, Aperol Spritz, **720 kcal**) in `meal-analysis-roger.jsonl`; `today_kcal`/`last_meal` sensors updated.
- **Wellness dashboard live** (sidebar tab `/wellness`): both cards render (`wellness-capture-card` + `wellness-assign-card`) via the global Lovelace resource collection, plus metrics + trend cards. No console errors.
- **Example automations imported**: `automation.wellness_measurement_reminder` + `automation.wellness_pending_scale_reading` (both `on`); Roger wired to `notify.rogers24` (derog_ha has no Companion device yet).

### Version history (bug fixes worth knowing)
- **0.4.0–0.4.2** — smart-scale hardening: `async_setup_weight_sensors()` was never awaited (subscription never registered); sensor values are now normalized to **kg** (g/lb/oz/st); the `number.*_body_weight` entity now mirrors coordinator changes so a scale auto-assign is reflected immediately.
- **0.5.0** — Groq model migration (`qwen/qwen3.6-27b`, llama-vision decommissioned), `<think>`-block stripping in the analyzer, `max_tokens` raised (qwen reasons verbosely).
- **0.1.1** — config flow: `MultiSelectSelector` doesn't exist in HA 2026.8 → `SelectSelector(multiple=True)`.
- **0.1.2** — config flow: `async_get_users()` must be awaited (500 on flow init).
- **0.1.3** — mount path selectable from configured NAS mounts; default `/share/wellness` (the old `/mnt/data/supervisor/mounts/...` path doesn't exist in the container namespace).

### Cards / dashboard notes
- Cards are deployed to `/config/www/wellness-{capture,assign}-card/`.
- **Lovelace resources live in the global `lovelace_resources` collection** (`.storage/lovelace_resources`, served by the `lovelace/resources` websocket) — a `resources:` array inside a storage dashboard config is **ignored** on HA 2026.8. Both card modules are registered there.
- Example dashboard YAML updated to the real entity IDs (`sensor.<user>_body_weight_statistics`, `sensor.pending_weight_assignments`).

---

## 6. Next steps (remaining)

1. **Verify the scale feed in real life** — step on the shared scale once; Samsung Health → S24+ → `sensor.s24plus_weight` should auto-assign to `roger` (last weight 118.0 kg). Trigger a deliberately ambiguous reading only if you want to see the "ask" flow again.
2. **Add derog_ha's Companion app** (when ready) so their reminder + pending-scale notifications work; fill `notify.mobile_app_<derog_ha_device>` in the automations (both example automations already have a commented placeholder).
3. **Optional hardening** — NFS fallback if the HA OS SMB mount fails to remount after reboots; consider versioning the HA `/config` in git.
4. HACS install path: the cards' `www/` resources can also be installed via HACS frontend repo so they auto-update; for now they're manually synced to `/config/www/`.

---

## 7. Secrets & credentials

| Secret | Where |
|---|---|
| Samba `homelab` password | `~/config/quadlets.env` on rack server (`USER=homelab;<pw>`) + HA OS mount config (`.storage`); **not in git** |
| Groq API key | **Configured** in the Wellness config entry `.storage` (added 2026-08-14); **not in git** — note it's stored in plaintext inside the HA config entry |
| DeepSeek key (from earlier) | Valid but **not usable for vision** (hosted API is text-only); kept for other uses |

---

## 8. Quick reference

- Repo: https://github.com/jaggr2/ha-wellness
- Releases: auto-tagged by `.github/workflows/release.yml` on manifest version bump.
- Server GitOps: `jaggr2/home-control-server-config` (wellness infra commit `74c152e`).
- Integration log name: `custom_components.wellness`.
