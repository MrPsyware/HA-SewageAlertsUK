const sections = {
  map: "River map", watch_point: "Watch point", markers: "Outfall markers",
  downstream: "Potential downstream paths", counts: "Status counts", warning: "Precautionary warning",
  countdown: "Time remaining", latest: "Latest discharge", outfalls: "Outfall list",
};
const defaults = Object.fromEntries(Object.keys(sections).map(key => [key, key !== "outfalls"]));
const isWatch = state => Array.isArray(state?.attributes.outfalls);
const point = ({ latitude, longitude }) => [latitude, longitude];
const valid = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[ch]);
const project = ([lat, lon], zoom) => {
  const size = 256 * 2 ** zoom;
  return [(lon + 180) / 360 * size, (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * size];
};
const status = site => site.status === "discharging" ? "Active" :
  site.status === "not_discharging" ? "Inactive" : "Unknown";

const colors = { red: "#ff6969", yellow: "#ffc446", green: "#5cd497", gray: "#a1a1aa" };
function outfallIndicator(site, hours, now, showWarning) {
  if (site.status === "discharging") return ["red", "Discharge reported"];
  if (site.status !== "not_discharging") return ["gray", "Report unavailable"];
  if (!showWarning) return ["green", "No active discharge reported"];
  const end = Date.parse(site.latest_end);
  const start = Date.parse(site.last_discharge);
  if (Number.isFinite(start) && (!Number.isFinite(end) || start > end)) {
    return ["gray", "Latest discharge end unknown"];
  }
  if (end + hours * 3600000 > now) return ["yellow", "Precautionary window"];
  return ["green", "No active discharge reported"];
}

class SewageAlertsUKCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.zoom = 0;
    this.shadowRoot.addEventListener("error", event => {
      if (event.target.matches(".tile")) {
        event.target.closest(".map").classList.add("tiles-unavailable");
      }
    }, true);
    this.shadowRoot.addEventListener("click", event => {
      const { zoom, site } = event.target.closest("[data-zoom], [data-site]")?.dataset ?? {};
      if (event.target.closest("[data-close-outfall]")) this.selected = null;
      else if (zoom) this.zoom = Math.max(-3, Math.min(3, this.zoom + Number(zoom)));
      else if (site !== undefined) this.selected = this.selected === site ? null : site;
      else return;
      this.render();
    });
    this.shadowRoot.addEventListener("keydown", event => {
      if (event.target.hasAttribute("data-site") && ["Enter", " "].includes(event.key)) {
        event.preventDefault();
        event.target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      }
    });
  }

  static getConfigElement() { return document.createElement("sewage-alerts-uk-card-editor"); }
  static getStubConfig(hass) {
    return { entity: Object.values(hass?.states ?? {}).find(s => s.entity_id.endsWith("_upstream_status") && isWatch(s))?.entity_id };
  }
  getCardSize() { return this.config?.show.map ? 6 : 2; }
  setConfig(config) {
    if (this.config?.entity !== config.entity) {
      this.zoom = 0;
      this.selected = null;
    }
    this.config = { ...config, show: { ...defaults, ...config.show } };
    this.render();
  }
  set hass(hass) {
    const entity = this.config?.entity;
    const changed = !this.home || this.home.states[entity] !== hass.states[entity];
    this.home = hass;
    this.toggleAttribute("dark", Boolean(hass.themes?.darkMode));
    if (changed || this.home.states[entity]?.attributes.outfalls?.some(site => !valid(point(site)))) this.render();
  }
  connectedCallback() { this.timer = setInterval(() => this.render(), 60000); }
  disconnectedCallback() { clearInterval(this.timer); }

  map(attributes, sites, show, now) {
    const origin = point(attributes);
    const lines = (attributes.river_geometry ?? []).filter(line => Array.isArray(line) && line.length > 1 && line.every(valid));
    const markers = sites.map((site, index) => ({ site, index, position: point(site) })).filter(m => valid(m.position));
    const points = [...lines.flat(), ...markers.map(m => m.position), ...(valid(origin) ? [origin] : [])];
    if (!points.length) return "<p>Map coordinates unavailable.</p>";
    const width = 640, height = 350;
    let zoom = 16;
    let bounds;
    const extent = z => {
      const pixels = points.map(p => project(p, z));
      return [Math.min(...pixels.map(p => p[0])), Math.min(...pixels.map(p => p[1])),
        Math.max(...pixels.map(p => p[0])), Math.max(...pixels.map(p => p[1]))];
    };
    while (zoom > 6) {
      bounds = extent(zoom);
      if (bounds[2] - bounds[0] <= width - 80 && bounds[3] - bounds[1] <= height - 80) break;
      zoom--;
    }
    zoom = Math.min(19, zoom + this.zoom);
    bounds = extent(zoom);
    const left = (bounds[0] + bounds[2] - width) / 2;
    const top = (bounds[1] + bounds[3] - height) / 2;
    const local = p => project(p, zoom).map((n, i) => Math.round(n - [left, top][i]));
    let tiles = "";
    for (let x = Math.floor(left / 256); x < (left + width) / 256; x++) {
      for (let y = Math.floor(top / 256); y < (top + height) / 256; y++) {
        const tileLeft = (x * 256 - left) / width * 100;
        const tileTop = (y * 256 - top) / height * 100;
        tiles += `<img class="tile" alt="" draggable="false" referrerpolicy="origin"
          style="left:${tileLeft}%;top:${tileTop}%;width:${256 / width * 100}%;height:${256 / height * 100}%"
          src="https://tile.openstreetmap.org/${zoom}/${x}/${y}.png">`;
      }
    }
    const dot = (p, color, label, index) => {
      const [x, y] = local(p);
      const action = index === undefined ? "" : `data-site="${index}" role="button" tabindex="0" aria-label="${escapeHtml(label)}"`;
      return `<circle cx="${x}" cy="${y}" r="8" fill="${color}" stroke="#172b40" stroke-width="2" ${action}><title>${escapeHtml(label)}</title></circle>`;
    };
    const drawLine = (line, color, weight, dash = "none") =>
      `<polyline points="${line.map(p => local(p).join(",")).join(" ")}" fill="none"
        stroke="${color}" stroke-width="${weight}" stroke-linecap="round" stroke-dasharray="${dash}"/>`;
    const activePaths = [];
    const precautionaryPaths = [];
    const selectedPaths = [];
    if (show.downstream) {
      sites.forEach((site, index) => {
        if (show.markers && this.selected != null && Number(this.selected) !== index) return;
        const paths = attributes.downstream_paths?.[`${site.provider}:${site.site_id}`] ?? [];
        const [tone] = outfallIndicator(site, attributes.contamination_window_hours ?? 96, now, show.warning);
        for (const line of paths) {
          if (!Array.isArray(line) || line.length < 2 || !line.every(valid)) continue;
          if (tone === "red") activePaths.push(drawLine(line, "#d96b26", 6));
          else if (tone === "yellow") precautionaryPaths.push(drawLine(line, "#ffc446", 6));
          else if (show.markers && Number(this.selected) === index && this.selected != null) {
            selectedPaths.push(drawLine(line, "#93ddff", 6, "5 5"));
          }
        }
      });
    }
    return `<div class="map">${tiles}<svg viewBox="0 0 ${width} ${height}" aria-label="Watched area map">
      ${lines.map(line => drawLine(line, "#087bd3", 4)).join("")}
      ${selectedPaths.join("")}${precautionaryPaths.join("")}${activePaths.join("")}
      ${show.watch_point && valid(origin) ? dot(origin, "#0094f2", "Watch point") : ""}
      ${show.markers ? markers.map(({ site, index, position }) => {
        const [tone, label] = outfallIndicator(site, attributes.contamination_window_hours ?? 96, now, show.warning);
        return dot(position, colors[tone], `${site.site_id} · ${label}`, index);
      }).join("") : ""}
      </svg><div class="zoom"><button data-zoom="1" aria-label="Zoom in">+</button><button data-zoom="-1" aria-label="Zoom out">−</button></div>
      <span class="tile-message">Basemap unavailable</span><a class="credits" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a></div>
      ${attributes.range_type === "upstream_river_distance" && !lines.length ? "<p>River trace available for newly set up watches.</p>" : ""}`;
  }

  render() {
    if (!this.config || !this.home) return;
    const { entity, show } = this.config;
    const watch = this.home.states[entity];
    if (!isWatch(watch)) {
      this.shadowRoot.innerHTML = "<ha-card style='padding:16px'>Select a Sewage Alerts UK watch in the card editor.</ha-card>";
      return;
    }
    const a = watch.attributes;
    const missingPositions = a.outfalls.some(site => !valid(point(site)));
    const markers = new Map();
    if (missingPositions && show.map) {
      for (const [id, state] of Object.entries(this.home.states)) {
        const marker = state.attributes;
        if (id.startsWith("geo_location.") &&
            ["sewage_alerts_uk", "sewage_alerts_uk_active"].includes(marker.source) && valid(point(marker))) {
          markers.set(JSON.stringify([marker.company, marker.site_id]), point(marker));
        }
      }
    }
    const sites = a.outfalls.map(site => {
      const position = markers.get(JSON.stringify([site.company, site.site_id]));
      return valid(point(site)) || !position ? site :
        { ...site, latitude: position[0], longitude: position[1] };
    });
    const available = watch.state !== "unavailable";
    const active = available && watch.state === "discharging";
    const until = available ? Date.parse(a.possible_contamination_until) : NaN;
    const now = Date.now();
    const minutes = Math.ceil((until - now) / 60000);
    const warning = active || minutes > 0 || (available && a.precautionary_warning === true && !Number.isFinite(until));
    const uncertain = !available || (a.precautionary_warning == null && !Number.isFinite(until));
    const [tone, icon, label] = active ? ["red", "alert-circle", "Discharge reported"] :
      show.warning && warning ? ["yellow", "clock-alert-outline", "Precautionary window"] :
      watch.state !== "no_reported_discharges" || (show.warning && uncertain) ?
        ["gray", "help-circle-outline", "Status unknown"] :
        ["green", "check-circle-outline", "No active discharges reported"];
    const countdown = !active && minutes > 0 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : "";
    const statusDetail = tone === "red" && show.warning ? "Discharge ongoing. Countdown starts after an end is reported." :
      tone === "yellow" ? (countdown && show.countdown ? `${countdown} remaining` : countdown ? "" : "End time unknown") : "";
    const tooltip = [label, statusDetail].filter(Boolean).join(" · ");
    const formatDate = date => date ? new Date(date).toLocaleString(this.home.language) : "No reported discharge";
    const latest = sites.map(site => site.last_discharge).filter(Boolean).sort().at(-1);
    const selected = sites[this.selected];
    const details = site => `<strong>${escapeHtml(site.site_id)}</strong> · ${escapeHtml(site.company)} · ${available ? status(site) : "Unknown"} · ${escapeHtml(site.distance_km)} km`;
    const outfallRow = site => {
      const [tone, description] = outfallIndicator(
        available ? site : { status: "unknown" }, a.contamination_window_hours ?? 96, now, show.warning
      );
      const label = { red: "Active", yellow: "Recent", green: "Inactive", gray: "Unknown" }[tone];
      return `<li class="outfall" style="--site-tone:${colors[tone]}">
        <div class="outfall-heading"><strong>${escapeHtml(site.site_id)}</strong>
          <span class="outfall-status" title="${escapeHtml(description)}">${label}</span></div>
        <small>${escapeHtml(site.company)} · ${escapeHtml(site.distance_km)} km</small>
        <small>Last active · ${escapeHtml(formatDate(site.last_discharge))}</small>
      </li>`;
    };
    const listOpen = this.shadowRoot.querySelector("ha-card > details")?.open;
    const indicatorOpen = this.shadowRoot.querySelector(".indicator")?.open;
    this.shadowRoot.innerHTML = `<style>
      ha-card{padding:18px;display:grid;gap:14px;color:var(--primary-text-color);container-type:inline-size;
        --panel:color-mix(in srgb,var(--primary-text-color) 7%,transparent)}
      h2,p{margin:0} h2{font-size:1.36rem;line-height:1.25} header{display:flex;align-items:center;gap:10px}
      header > ha-icon{color:#54b8fc} .detail{padding:12px;border-radius:10px;background:var(--panel)}
      .indicator{position:relative;margin-inline-start:auto;color:var(--tone);flex-shrink:0}
      .indicator summary{list-style:none;display:flex;align-items:center;gap:5px;padding:4px}
      .indicator summary::-webkit-details-marker{display:none}
      .indicator small{color:var(--tone);white-space:nowrap}
      .indicator p{position:absolute;right:0;top:100%;width:max-content;max-width:200px;z-index:2;
        padding:8px 10px;border-radius:8px;background:var(--card-background-color,#20242a);
        border:1px solid var(--divider-color)}
      .counts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border:1px solid var(--divider-color);border-radius:10px}
      .count{padding:8px 4px;text-align:center}.count+.count{border-inline-start:1px solid var(--divider-color)}
      .count strong{display:block;font-size:1.15rem}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-inline-end:5px;background:var(--dot)}
      .map{position:relative;overflow:hidden;border-radius:12px;background:var(--panel);isolation:isolate}
      svg{display:block;width:100%;position:relative} circle[data-site]{cursor:pointer}
      .tile{position:absolute;display:block;pointer-events:none;filter:var(--map-tile-filter,none)}
      :host([dark]) .tile{filter:brightness(.64) saturate(.62)}
      .tiles-unavailable .tile{visibility:hidden}
      .tile-message{display:none;position:absolute;bottom:6px;left:8px;font-size:11px;color:var(--secondary-text-color)}
      .tiles-unavailable .tile-message{display:block}
      .zoom{position:absolute;top:8px;left:8px;display:grid;gap:3px}
      button{font:inherit;cursor:pointer} .zoom button{width:32px;height:32px;border:1px solid var(--divider-color);
        border-radius:6px;color:var(--primary-text-color);background:var(--card-background-color,#20242a)}
      .credits{position:absolute;right:0;bottom:0;background:#182431;color:#fff;padding:2px 4px;font-size:10px}
      ul{padding:0;margin:10px 0 0;list-style:none;display:grid;gap:6px}
      .outfall{padding:8px 10px;border-inline-start:3px solid var(--site-tone);border-radius:6px;
        background:color-mix(in srgb,var(--site-tone) 9%,transparent)}
      .outfall-heading{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
      .outfall small{display:block;margin-top:3px}
      .outfall-status{color:var(--primary-text-color);font-weight:600}
      .outfall-status::before{content:"";display:inline-block;width:7px;height:7px;margin-inline-end:5px;
        border-radius:50%;background:var(--site-tone)}
      .detail{position:relative;padding-inline-end:44px}
      .detail-close{position:absolute;inset-inline-end:8px;top:8px;width:30px;height:30px;
        border:0;border-radius:6px;background:transparent;color:var(--primary-text-color);font-size:20px}
      .detail-close:hover{background:var(--panel)}
      summary{cursor:pointer} small,p{color:var(--secondary-text-color)} .warning small{color:inherit}
      </style><ha-card>
      <header><ha-icon icon="mdi:waves"></ha-icon><h2>${escapeHtml(this.config.title || `${a.river} watch`)}</h2>
      <details class="indicator" style="--tone:${colors[tone]}" ${indicatorOpen ? "open" : ""}>
        <summary title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}"><ha-icon icon="mdi:${icon}"></ha-icon>
        ${tone === "yellow" && show.countdown && countdown ? `<small>${countdown}</small>` : ""}</summary>
        <p>${escapeHtml(tooltip)}</p></details></header>
      ${show.counts ? `<div class="counts">${["Active", "Inactive", "Unknown"].map(label =>
        `<div class="count"><strong>${sites.filter(site => (available ? status(site) : "Unknown") === label).length}</strong><small><span class="dot" style="--dot:${{Active:"#ff6969",Inactive:"#83a9c4",Unknown:"#a1a1aa"}[label]}"></span>${label}</small></div>`).join("")}</div>` : ""}
      ${show.map ? this.map(a, available ? sites : sites.map(site => ({ ...site, status: "unknown" })), show, now) : ""}
      ${show.map && show.markers && selected ? `<div class="detail"><button type="button" class="detail-close" data-close-outfall aria-label="Close outfall details" title="Close outfall details">×</button>${details(selected)}<br><small>Latest discharge: ${escapeHtml(formatDate(selected.last_discharge))}<br>${outfallIndicator(available ? selected : { status: "unknown" }, a.contamination_window_hours ?? 96, now, show.warning)[1]}</small></div>` : ""}
      ${show.latest ? `<p>Latest discharge · ${escapeHtml(available ? formatDate(latest) : "Unavailable")}</p>` : ""}
      ${show.outfalls ? `<details ${listOpen ? "open" : ""}><summary>Outfalls (${sites.length})</summary><ul>${sites.map(outfallRow).join("")}</ul></details>` : ""}
      </ha-card>`;
  }
}

class SewageAlertsUKCardEditor extends HTMLElement {
  setConfig(config) { this.config = config; this.render(); }
  set hass(hass) {
    this.home = hass;
    if (!this.firstChild) this.render();
  }
  render() {
    if (!this.config || !this.home) return;
    const options = Object.values(this.home.states).filter(s => s.entity_id.startsWith("sensor.") &&
      (Object.hasOwn(s.attributes, "precautionary_warning") || (s.entity_id.endsWith("_upstream_status") && isWatch(s))));
    this.innerHTML = `<style>sewage-alerts-uk-card-editor label{display:block;padding:8px} sewage-alerts-uk-card-editor select{max-width:100%}</style>
      <label>Watch <select name="entity"><option value="">Select a watch</option>
      ${options.map(s => `<option value="${escapeHtml(s.entity_id)}" ${s.entity_id === this.config.entity ? "selected" : ""}>${escapeHtml(s.attributes.friendly_name ?? s.entity_id)}</option>`).join("")}
      </select></label>${Object.entries(sections).map(([key, title]) => `<label>
        <input type="checkbox" name="${key}" ${(this.config.show?.[key] ?? defaults[key]) ? "checked" : ""}> ${title}</label>`).join("")}`;
    this.onchange = ({ target }) => {
      this.config = target.name === "entity" ? { ...this.config, entity: target.value } :
        { ...this.config, show: { ...this.config.show, [target.name]: target.checked } };
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this.config }, bubbles: true, composed: true }));
    };
  }
}

customElements.define("sewage-alerts-uk-card", SewageAlertsUKCard);
customElements.define("sewage-alerts-uk-card-editor", SewageAlertsUKCardEditor);
(window.customCards ??= []).push({
  type: "sewage-alerts-uk-card",
  name: "Sewage Alerts UK",
  description: "Live watch map, reported discharges and precautionary window.",
});
