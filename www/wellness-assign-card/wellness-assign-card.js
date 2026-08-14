/* Wellness assign card — resolve unassigned smart-scale readings.
 *
 * Reads sensor.wellness_pending (count + pending details), shows each reading
 * with a participant dropdown, and assigns/dismisses via the wellness
 * services. Intended for admins who get notified on ambiguity.
 */

class WellnessAssignCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._selected = {};
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  _pending() {
    if (!this._hass) return [];
    const st = this._hass.states["sensor.wellness_pending"];
    if (!st || !st.attributes || !st.attributes.pending) return [];
    return st.attributes.pending;
  }

  _render() {
    if (!this._hass) return;
    const pending = this._pending();
    const rows = pending.map((item) => {
      const opts = (item.participants || []).map(
        (p) => `<option value="${p.slug}">${p.name}</option>`
      ).join("");
      const selected = this._selected[item.id] || (item.candidates && item.candidates[0] && item.candidates[0].slug) || "";
      const hint = (item.candidates && item.candidates.length)
        ? `within ±5 kg of: ${item.candidates.map((c) => c.name).join(", ")}`
        : "no one is within ±5 kg of their last weight — pick manually";
      return `
        <div style="border:1px solid var(--divider-color,#e0e0e0);border-radius:8px;padding:10px;margin-bottom:8px">
          <div style="font-weight:500">⚖️ ${item.weight_kg} kg</div>
          <div style="font-size:12px;color:#888">${item.ts || ""} · ${hint}</div>
          <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
            <select data-id="${item.id}" style="flex:1;min-width:0">
              <option value="" ${selected ? "" : "selected"}>— choose —</option>
              ${opts}
            </select>
            <mwc-button raised data-assign="${item.id}" ?disabled="${!selected}">Assign</mwc-button>
            <mwc-button data-dismiss="${item.id}">Dismiss</mwc-button>
          </div>
        </div>`;
    }).join("");

    this.innerHTML = `
      <ha-card>
        <div style="padding:16px">
          <div style="font-weight:500;margin-bottom:8px">
            ⚖️ Unassigned scale readings (${pending.length})
          </div>
          ${pending.length ? rows : '<div style="color:#888;font-size:13px">Nothing pending.</div>'}
        </div>
      </ha-card>`;

    this.querySelectorAll("select").forEach((sel) => {
      sel.addEventListener("change", () => {
        this._selected[sel.dataset.id] = sel.value;
      });
    });
    this.querySelectorAll("mwc-button[data-assign]").forEach((btn) => {
      btn.addEventListener("click", () => this._assign(btn.dataset.assign));
    });
    this.querySelectorAll("mwc-button[data-dismiss]").forEach((btn) => {
      btn.addEventListener("click", () => this._dismiss(btn.dataset.dismiss));
    });
  }

  _assign(id) {
    const slug = this._selected[id];
    if (!slug) return;
    this._hass.callService("wellness", "assign_weight", { reading_id: id, user: slug });
  }

  _dismiss(id) {
    this._hass.callService("wellness", "dismiss_weight", { reading_id: id });
  }
}

customElements.define("wellness-assign-card", WellnessAssignCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wellness-assign-card",
  name: "Wellness assign",
  description: "Resolve unassigned smart-scale readings (admins)",
});
