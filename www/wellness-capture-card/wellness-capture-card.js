/* Wellness capture card — one-tap camera capture of a meal photo.
 *
 * Opens the phone camera (Android Companion app supports <input type=file>
 * camera capture), resizes the photo in-browser, and uploads it to the
 * authenticated /api/wellness/photo endpoint. The participant is resolved
 * server-side from the logged-in HA account.
 */

class WellnessCaptureCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._status = "";
    this._thumb = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  _render() {
    if (!this._hass) return;
    const user = this._hass.user ? this._hass.user.name : "";
    const statusColor = this._status === "ok" ? "#4caf50"
      : this._status === "err" ? "#f44336" : "#888";
    const statusText = this._status === "ok" ? "Photo saved"
      : this._status === "err" ? this._error || "Upload failed"
      : this._status === "busy" ? "Uploading…" : "";

    this.innerHTML = `
      <ha-card>
        <div style="padding:16px">
          <div style="font-weight:500;margin-bottom:8px">
            📷 Meal photo${user ? ` · ${user}` : ""}
          </div>
          <mwc-button raised>
            <slot>Take photo</slot>
          </mwc-button>
          <input type="file" accept="image/*" capture="environment"
                 style="display:none">
          ${this._thumb ? `<div style="margin-top:8px"><img src="${this._thumb}" style="max-height:120px;border-radius:8px"></div>` : ""}
          ${statusText ? `<div style="margin-top:8px;color:${statusColor};font-size:12px">${statusText}</div>` : ""}
        </div>
      </ha-card>`;

    const input = this.querySelector("input");
    this.querySelector("button, mwc-button").addEventListener("click", () => input.click());
    input.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) this._upload(file);
      input.value = "";
    });
  }

  _resize(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("read failed"));
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error("decode failed"));
        img.onload = () => {
          const max = this._config.max_size || 1600;
          let { width, height } = img;
          if (width > height && width > max) { height = Math.round(height * max / width); width = max; }
          else if (height > max) { width = Math.round(width * max / height); height = max; }
          const canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          canvas.getContext("2d").drawImage(img, 0, 0, width, height);
          canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("encode failed")), "image/jpeg", 0.8);
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  _upload(file) {
    this._status = "busy";
    this._render();
    this._doUpload(file).catch((err) => {
      this._status = "err";
      this._error = err && err.message ? err.message : String(err);
      this._render();
    });
  }

  _accessToken() {
    // The Companion app / HA frontend keeps the token in auth.data;
    // fall back to the legacy auth.access_token for older frontends.
    const auth = this._hass && this._hass.auth;
    if (!auth) return null;
    if (auth.data && auth.data.access_token) return auth.data.access_token;
    if (auth.access_token) return auth.access_token;
    return null;
  }

  async _doUpload(file) {
    const blob = await this._resize(file);
    const form = new FormData();
    form.append("file", blob, "meal.jpg");
    const token = this._accessToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const resp = await fetch("/api/wellness/photo", { method: "POST", headers, body: form });
    if (!resp.ok) {
      let msg = `HTTP ${resp.status}`;
      try { const j = await resp.json(); msg = j.message || j.error || msg; } catch (_) {}
      throw new Error(msg);
    }
    const url = URL.createObjectURL(blob);
    this._thumb = url;
    this._status = "ok";
    this._error = "";
    this._render();
  }
}

customElements.define("wellness-capture-card", WellnessCaptureCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wellness-capture-card",
  name: "Wellness capture",
  description: "One-tap meal photo capture for the Wellness integration",
});
