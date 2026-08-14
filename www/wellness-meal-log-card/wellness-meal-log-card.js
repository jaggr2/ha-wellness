/* Wellness meal log card — list recent meals with analysis + delete.
 *
 * Fetches GET /api/wellness/meals (authenticated; participant resolved
 * server-side) and shows each meal with its photo, timestamp, detected food
 * and estimated kcal. A delete button removes the entry via the
 * wellness.delete_meal service.
 */

class WellnessMealLogCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._meals = [];
    this._thumbs = {};
    this._loading = false;
    this._error = "";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loadedOnce) {
      this._loadedOnce = true;
      this._load();
    }
    this._render();
  }

  getCardSize() {
    return 4;
  }

  _accessToken() {
    const auth = this._hass && this._hass.auth;
    if (!auth) return null;
    if (auth.data && auth.data.access_token) return auth.data.access_token;
    if (auth.access_token) return auth.access_token;
    return null;
  }

  async _load() {
    this._loading = true;
    this._error = "";
    this._render();
    try {
      const token = this._accessToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const params = new URLSearchParams();
      params.set("limit", String(this._config.limit || 10));
      if (this._config.user) params.set("user", this._config.user);
      const resp = await fetch("/api/wellness/meals?" + params.toString(), { headers });
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { const j = await resp.json(); msg = j.message || j.error || msg; } catch (_) {}
        throw new Error(msg);
      }
      const data = await resp.json();
      this._meals = data.meals || [];
    } catch (err) {
      this._error = err && err.message ? err.message : String(err);
    }
    this._loading = false;
    this._render();
    this._loadThumbs();
  }

  async _loadThumbs() {
    const token = this._accessToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    for (const meal of this._meals) {
      if (!meal.photo || this._thumbs && this._thumbs[meal.photo]) continue;
      const params = new URLSearchParams({ path: meal.photo });
      if (this._config.user) params.set("user", this._config.user);
      try {
        const resp = await fetch("/api/wellness/photo?" + params.toString(), { headers });
        if (!resp.ok) continue;
        const blob = await resp.blob();
        if (!this._thumbs) this._thumbs = {};
        this._thumbs[meal.photo] = URL.createObjectURL(blob);
        this._render();
      } catch (_) {
        /* thumbnail best effort */
      }
    }
  }

  _delete(photo) {
    if (!window.confirm("Delete this meal?")) return;
    const token = this._accessToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const body = { photo };
    if (this._config.user) body.user = this._config.user;
    fetch("/api/wellness/meal/delete", {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(() => this._load()).catch(() => this._load());
  }

  _fmtTime(ts) {
    if (!ts) return "";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  _render() {
    if (!this._hass) return;

    let body = "";
    if (this._loading) {
      body = '<div style="color:#888;font-size:13px">Loading…</div>';
    } else if (this._error) {
      body = `<div style="color:#f44336;font-size:13px">${this._error}</div>`;
    } else if (!this._meals.length) {
      body = '<div style="color:#888;font-size:13px">No meals logged yet.</div>';
    } else {
      body = this._meals.map((meal) => {
        const food = (meal.food || []).join(", ");
        const kcal = meal.estimated_kcal_total;
        const kcalHtml = kcal != null
          ? `<span style="color:#4caf50;font-weight:500">${kcal} kcal</span>`
          : '<span style="color:#888">not analyzed</span>';
        return `
          <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--divider-color,#e0e0e0)">
            <div style="flex:0 0 48px;height:48px;border-radius:6px;overflow:hidden;background:#eee">
              <img src="${this._thumbs && this._thumbs[meal.photo] || ""}"
                   style="width:48px;height:48px;object-fit:cover"
                   onerror="this.style.display='none'">
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-size:12px;color:#888">${this._fmtTime(meal.ts)}</div>
              <div style="font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${food || "—"}</div>
              <div>${kcalHtml}</div>
            </div>
            <mwc-button data-delete="${meal.photo}" style="--mdc-theme-primary:#f44336">Delete</mwc-button>
          </div>`;
      }).join("");
    }

    this.innerHTML = `
      <ha-card>
        <div style="padding:16px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <div style="font-weight:500">🍽️ Recent meals</div>
            <mwc-button data-refresh>Refresh</mwc-button>
          </div>
          ${body}
        </div>
      </ha-card>`;

    this.querySelector("[data-refresh]").addEventListener("click", () => this._load());
    this.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", () => this._delete(btn.dataset.delete));
    });
  }
}

customElements.define("wellness-meal-log-card", WellnessMealLogCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wellness-meal-log-card",
  name: "Wellness meal log",
  description: "List recent meals with analysis and delete wrong entries",
});
