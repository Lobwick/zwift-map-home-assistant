/**
 * zwift-map-card — the Zwift route you are riding: map, elevation profile and
 * live numbers, readable from the bike.
 *
 *   type: custom:zwift-map-card
 *   entity: sensor.zwift_map_live
 *   zone_color_entity: light.zwift_<name>_power_zone_color   # optional
 *   ftp_entity: sensor.zwift_<name>_ftp                      # optional (or ftp: 252)
 *   layout: auto | portrait | landscape                      # default auto
 *   map_rotate: 0 | 90 | 180 | 270                           # default 0
 *   map_mirror: false
 *   show_map / show_profile / show_stats: true
 */

const CARD_VERSION = "0.1.0";

const I18N = {
  en: {
    offline: "Not riding on Zwift",
    free_ride: "Free ride",
    lead_in: "Lead-in",
    finished: "Finished",
    unknown_route: "Route",
    lap: "Lap",
    to_go: "to go",
    recording: "Recording the route — the map completes as you ride it",
    no_track: "Ride this route once to draw its map",
    rpm: "rpm",
    bpm: "bpm",
    kmh: "km/h",
    grade: "grade",
  },
  fr: {
    offline: "Pas sur Zwift",
    free_ride: "Free ride",
    lead_in: "Lead-in",
    finished: "Terminée",
    unknown_route: "Route",
    lap: "Tour",
    to_go: "restants",
    recording: "Enregistrement de la route — la carte se complète en roulant",
    no_track: "Roule cette route une fois pour dessiner sa carte",
    rpm: "rpm",
    bpm: "bpm",
    kmh: "km/h",
    grade: "pente",
  },
};

// Zwift's power zones, as % of FTP, and their colours.
const ZONES = [
  [60, "#8a8f98"],
  [76, "#2f7cf6"],
  [90, "#38b24a"],
  [105, "#f2c418"],
  [119, "#f47b20"],
  [Infinity, "#e8312f"],
];

const SVG_NS = "http://www.w3.org/2000/svg";
const MAP_W = 1000;
const MAP_H = 640;
const PROF_W = 1000;
const PROF_H = 220;
const TRAIL_MAX = 4000;

const STYLE = `
  :host { display: block; height: 100%; }
  ha-card {
    height: 100%;
    box-sizing: border-box;
    --zm-bg: var(--ha-card-background, var(--card-background-color, #14161a));
    --zm-fg: var(--primary-text-color, #f2f3f5);
    --zm-dim: var(--secondary-text-color, #9aa0a8);
    --zm-road: color-mix(in srgb, var(--zm-fg) 22%, transparent);
    --zm-done: var(--zm-accent, #f47b20);
    --zm-zone: #8a8f98;
    overflow: hidden;
    color: var(--zm-fg);
    container-type: inline-size;
  }
  .wrap { display: grid; gap: 12px; padding: 14px; box-sizing: border-box; height: 100%;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto auto auto minmax(240px, 1fr) auto;
    grid-template-areas: "head" "power" "stats" "map" "profile"; }
  .wrap.landscape { grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr);
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    grid-template-areas: "head head" "power map" "stats map" "profile profile"; }
  .wrap.landscape .power, .wrap.landscape .stats { align-self: start; }
  .wrap.landscape .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .head { grid-area: head; display: flex; align-items: baseline; gap: 12px; min-width: 0; }
  .title { font-size: clamp(20px, 5.5cqi, 34px); font-weight: 700; line-height: 1.1;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1 1 auto; min-width: 0; }
  .sub { font-size: clamp(13px, 3.4cqi, 18px); color: var(--zm-dim); white-space: nowrap; }
  .power { grid-area: power; border-radius: 14px; padding: 10px 16px; display: flex; align-items: baseline;
    justify-content: center; gap: 8px; background: var(--zm-zone); color: #fff; transition: background .4s; }
  .power .v { font-size: clamp(56px, 19cqi, 120px); font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
  .power .u { font-size: clamp(18px, 5cqi, 32px); font-weight: 700; opacity: .85; }
  .stats { grid-area: stats; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .stat { background: color-mix(in srgb, var(--zm-fg) 7%, transparent); border-radius: 12px; padding: 8px 6px; text-align: center; }
  .stat .v { font-size: clamp(24px, 8cqi, 44px); font-weight: 700; line-height: 1.05; font-variant-numeric: tabular-nums; }
  .stat .u { font-size: clamp(11px, 2.8cqi, 15px); color: var(--zm-dim); text-transform: uppercase; letter-spacing: .04em; }
  .map { grid-area: map; position: relative; min-height: 0; }
  .map svg { display: block; width: 100%; height: 100%; min-height: 240px; }
  .profile { grid-area: profile; position: relative; }
  .profile svg { display: block; width: 100%; height: clamp(110px, 16cqi, 170px); }
  .wrap.landscape .profile svg { height: 120px; }
  .plabels { display: flex; justify-content: space-between; align-items: baseline;
    font-weight: 800; font-variant-numeric: tabular-nums; margin-bottom: 2px; }
  .plabels .g { font-size: clamp(26px, 7cqi, 40px); }
  .plabels .f { font-size: clamp(18px, 4.5cqi, 26px); }
  .note { position: absolute; left: 8%; right: 8%; top: 50%; transform: translateY(-50%); text-align: center;
    font-size: clamp(14px, 3.6cqi, 20px); color: var(--zm-dim); pointer-events: none; }
  .note.recording { top: auto; bottom: 4px; transform: none; font-size: 13px; }
  .bar { height: 6px; border-radius: 3px; background: var(--zm-road); overflow: hidden; margin-top: 6px; }
  .bar > i { display: block; height: 100%; width: 0; background: var(--zm-done); transition: width .6s linear; }
  .offline { padding: 28px 16px; text-align: center; color: var(--zm-dim); font-size: 18px; }
  .hidden { display: none !important; }
  .road { fill: none; stroke: var(--zm-road); stroke-linecap: round; stroke-linejoin: round; }
  .done { fill: none; stroke: var(--zm-done); stroke-linecap: round; stroke-linejoin: round; }
  .trail { fill: none; stroke: var(--zm-done); stroke-opacity: .9; stroke-linecap: round; stroke-linejoin: round; }
  .me { fill: var(--zm-done); stroke: #fff; }
  .halo { fill: var(--zm-done); fill-opacity: .25; }
  .area { fill: color-mix(in srgb, var(--zm-fg) 14%, transparent); }
  .area-done { fill: color-mix(in srgb, var(--zm-done) 55%, transparent); }
  .line { fill: none; stroke: color-mix(in srgb, var(--zm-fg) 45%, transparent); stroke-width: 2; }
  .cursor { stroke: #fff; stroke-width: 3; vector-effect: non-scaling-stroke; }
  .line { vector-effect: non-scaling-stroke; }
`;

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function polyline(points) {
  let out = "";
  for (let i = 0; i < points.length; i++) {
    out += (i ? "L" : "M") + points[i][0].toFixed(1) + " " + points[i][1].toFixed(1);
  }
  return out;
}

class ZwiftMapCard extends HTMLElement {
  static getStubConfig(hass) {
    const live = Object.keys(hass.states).find((e) => /^sensor\.zwift_map.*live$/.test(e));
    const zone = Object.keys(hass.states).find((e) => /^light\.zwift_.*power_zone_color$/.test(e));
    return { entity: live || "sensor.zwift_map_live", ...(zone ? { zone_color_entity: zone } : {}) };
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("entity is required (sensor.zwift_map_live)");
    this._config = {
      layout: "auto",
      map_rotate: 0,
      map_mirror: false,
      show_map: true,
      show_profile: true,
      show_stats: true,
      ...config,
    };
    this._built = false;
    this._trackKey = null;
    this._trail = [];
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, rows: "auto", min_columns: 6 };
  }

  connectedCallback() {
    if (!this._ro) {
      this._ro = new ResizeObserver(() => this._applyLayout());
    }
    this._ro.observe(this);
  }

  disconnectedCallback() {
    this._ro?.disconnect();
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return (I18N[lang] || I18N.en)[key] ?? I18N.en[key];
  }

  _build() {
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="offline hidden"></div>
        <div class="wrap">
          <div class="head"><div class="title"></div><div class="sub"></div></div>
          <div class="power"><span class="v">–</span><span class="u">W</span></div>
          <div class="stats">
            <div class="stat"><div class="v" data-k="cad">–</div><div class="u">${this._t("rpm")}</div></div>
            <div class="stat"><div class="v" data-k="hr">–</div><div class="u">${this._t("bpm")}</div></div>
            <div class="stat"><div class="v" data-k="spd">–</div><div class="u">${this._t("kmh")}</div></div>
            <div class="stat"><div class="v" data-k="grd">–</div><div class="u">% ${this._t("grade")}</div></div>
          </div>
          <div class="map"><svg viewBox="0 0 ${MAP_W} ${MAP_H}" preserveAspectRatio="xMidYMid meet"></svg><div class="note hidden"></div></div>
          <div class="profile">
            <div class="plabels"><span class="g"></span><span class="f"></span></div>
            <svg viewBox="0 0 ${PROF_W} ${PROF_H}" preserveAspectRatio="none"></svg>
            <div class="bar"><i></i></div>
          </div>
        </div>
      </ha-card>`;
    const $ = (s) => root.querySelector(s);
    this._els = {
      card: $("ha-card"),
      offline: $(".offline"),
      wrap: $(".wrap"),
      title: $(".title"),
      sub: $(".sub"),
      power: $(".power"),
      powerV: $(".power .v"),
      stats: $(".stats"),
      cad: $('[data-k="cad"]'),
      hr: $('[data-k="hr"]'),
      spd: $('[data-k="spd"]'),
      grd: $('[data-k="grd"]'),
      map: $(".map"),
      mapSvg: $(".map svg"),
      note: $(".map .note"),
      profile: $(".profile"),
      profSvg: $(".profile svg"),
      pGrade: $(".plabels .g"),
      pFlag: $(".plabels .f"),
      bar: $(".bar > i"),
    };
    this._built = true;
    this._applyLayout();
  }

  _applyLayout() {
    if (!this._built) return;
    const mode = this._config.layout;
    const landscape =
      mode === "landscape" ||
      (mode === "auto" && this.clientWidth > 0 && this.clientWidth > 1.15 * (this.clientHeight || 0) && this.clientWidth >= 700);
    this._els.wrap.classList.toggle("landscape", landscape);
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._built) this._build();
    const e = this._els;
    const st = this._hass.states[this._config.entity];
    e.map.classList.toggle("hidden", !this._config.show_map);
    e.profile.classList.toggle("hidden", !this._config.show_profile);
    e.stats.classList.toggle("hidden", !this._config.show_stats);

    if (!st || st.state === "offline" || st.state === "unavailable" || st.state === "unknown") {
      e.offline.textContent = st ? this._t("offline") : `${this._config.entity} ?`;
      e.offline.classList.remove("hidden");
      e.wrap.classList.add("hidden");
      this._trail = [];
      return;
    }
    e.offline.classList.add("hidden");
    e.wrap.classList.remove("hidden");
    const a = st.attributes;

    // Header
    const phase = st.state;
    e.title.textContent = a.route_name || this._t(phase === "free_ride" ? "free_ride" : "unknown_route");
    const parts = [];
    if (a.world) parts.push(a.world);
    if (phase === "lead_in") parts.push(this._t("lead_in"));
    else if (phase === "finished") parts.push(this._t("finished"));
    else if (a.lap_route && a.lap > 1) parts.push(`${this._t("lap")} ${a.lap}`);
    if (a.remaining_m != null) parts.push(`🏁 ${(a.remaining_m / 1000).toFixed(1)} km`);
    e.sub.textContent = parts.join(" · ");

    // Numbers
    e.powerV.textContent = a.power_w ?? "–";
    e.cad.textContent = a.cadence_rpm ?? "–";
    e.hr.textContent = a.heart_rate ? a.heart_rate : "–";
    e.spd.textContent = a.speed_kmh != null ? Math.round(a.speed_kmh) : "–";
    e.grd.textContent = a.gradient_pct != null ? Number(a.gradient_pct).toFixed(1) : "–";
    const zone = this._zoneColor(a.power_w);
    e.card.style.setProperty("--zm-zone", zone);
    e.card.style.setProperty("--zm-accent", this._config.accent_color || "#f47b20");

    // Route geometry
    const key = `${a.route_id || 0}:${a.track_version}`;
    if (key !== this._trackKey) {
      if ((a.route_id || 0) !== this._trackRoute) this._trail = [];
      this._trackKey = key;
      this._trackRoute = a.route_id || 0;
      this._loadTrack(a.route_id, a);
    }
    if (a.x != null && a.z != null) {
      const last = this._trail[this._trail.length - 1];
      if (!last || last[0] !== a.x || last[1] !== a.z) {
        this._trail.push([a.x, a.z]);
        if (this._trail.length > TRAIL_MAX) this._trail.shift();
      }
    }
    this._renderLive(a);
  }

  _zoneColor(power) {
    const ent = this._config.zone_color_entity && this._hass.states[this._config.zone_color_entity];
    const rgb = ent?.attributes?.rgb_color;
    if (Array.isArray(rgb) && rgb.length === 3) return `rgb(${rgb.join(",")})`;
    let ftp = Number(this._config.ftp);
    if (this._config.ftp_entity) ftp = Number(this._hass.states[this._config.ftp_entity]?.state);
    if (!ftp || power == null) return ZONES[0][1];
    const pct = (power / ftp) * 100;
    return ZONES.find(([max]) => pct < max)[1];
  }

  async _loadTrack(routeId, attrs) {
    const want = this._trackKey;
    let track = null;
    if (routeId) {
      try {
        track = await this._hass.callApi("GET", `zwift_map/track/${routeId}`);
      } catch (_err) {
        track = null;
      }
    }
    if (want !== this._trackKey) return; // a newer request superseded this one
    this._track = track && Array.isArray(track.points) && track.points.length > 1 ? track : null;
    this._drawStatic(attrs);
  }

  // Project game coordinates (x, z) into the map's viewBox.
  _projector(points) {
    const rot = ((Number(this._config.map_rotate) % 360) + 360) % 360;
    const mirror = Boolean(this._config.map_mirror);
    const turn = ([x, z]) => {
      let p = [x, z];
      if (mirror) p = [-p[0], p[1]];
      if (rot === 90) p = [-p[1], p[0]];
      else if (rot === 180) p = [-p[0], -p[1]];
      else if (rot === 270) p = [p[1], -p[0]];
      return p;
    };
    const pts = points.map(turn);
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const [x, y] of pts) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    const pad = 40;
    const w = Math.max(maxX - minX, 1);
    const h = Math.max(maxY - minY, 1);
    const s = Math.min((MAP_W - 2 * pad) / w, (MAP_H - 2 * pad) / h);
    const ox = (MAP_W - w * s) / 2;
    const oy = (MAP_H - h * s) / 2;
    return (p) => {
      const [x, y] = turn(p);
      return [ox + (x - minX) * s, oy + (y - minY) * s];
    };
  }

  _drawStatic(attrs) {
    const e = this._els;
    const map = e.mapSvg;
    const prof = e.profSvg;
    map.replaceChildren();
    prof.replaceChildren();
    this._live = {};
    const track = this._track;
    const length = attrs.route_length_m || track?.length_m || 0;

    // ---- map
    if (track) {
      const pts = track.points.map((p) => [p[1], p[2]]);
      this._project = this._projector(pts);
      const d = polyline(pts.map(this._project));
      el("path", { d, class: "road", "stroke-width": 26 }, map);
      // Distance-proportional dash: points are evenly spaced along the road.
      const onRoute = track.points.filter((p) => p[0] >= 0).map((p) => this._project([p[1], p[2]]));
      this._live.done = el("path", { d: polyline(onRoute), class: "done", "stroke-width": 14, pathLength: 1000, "stroke-dasharray": "0 1000" }, map);
    } else {
      this._project = null;
    }
    this._live.trail = el("path", { class: "trail", "stroke-width": 10 }, map);
    this._live.halo = el("circle", { r: 34, class: "halo" }, map);
    this._live.me = el("circle", { r: 16, class: "me", "stroke-width": 5 }, map);

    const coverage = track?.coverage ?? 0;
    e.note.textContent = track ? this._t("recording") : this._t("no_track");
    e.note.classList.toggle("recording", Boolean(track));
    e.note.classList.toggle("hidden", Boolean(track) && coverage >= 0.98);

    // ---- profile
    const prPts = track ? track.points.filter((p) => p[0] >= 0 && p[0] <= length) : [];
    if (prPts.length > 1 && length) {
      let lo = Infinity, hi = -Infinity;
      for (const p of prPts) {
        if (p[3] < lo) lo = p[3];
        if (p[3] > hi) hi = p[3];
      }
      const range = Math.max(hi - lo, 20);
      const top = 12;
      this._py = (alt) => PROF_H - 8 - ((alt - lo) / range) * (PROF_H - top);
      const line = prPts.map((p) => [(p[0] / length) * PROF_W, this._py(p[3])]);
      const area = polyline(line) + `L${PROF_W} ${PROF_H}L0 ${PROF_H}Z`;
      const clip = el("clipPath", { id: "zm-done" }, el("defs", {}, prof));
      this._live.clip = el("rect", { x: 0, y: 0, width: 0, height: PROF_H }, clip);
      el("path", { d: area, class: "area" }, prof);
      el("path", { d: area, class: "area-done", "clip-path": "url(#zm-done)" }, prof);
      el("path", { d: polyline(line), class: "line" }, prof);
      this._profPts = prPts;
    } else {
      this._py = null;
      this._profPts = null;
    }
    this._live.cursor = el("line", { y1: 0, y2: PROF_H, class: "cursor" }, prof);
    this._renderLive(attrs);
  }

  _renderLive(a) {
    const L = this._live;
    if (!L || !L.me) return;
    const length = a.route_length_m || this._track?.length_m || 0;
    const along = a.lap_distance_m != null ? Math.max(0, a.lap_distance_m) : 0;
    const frac = length ? Math.min(along / length, 1) : 0;

    // Map: projection from the stored track, or from the live trail if none yet.
    let project = this._project;
    if (!project && this._trail.length > 1) project = this._projector(this._trail);
    if (project && a.x != null) {
      const [mx, my] = project([a.x, a.z]);
      for (const c of [L.me, L.halo]) {
        c.setAttribute("cx", mx.toFixed(1));
        c.setAttribute("cy", my.toFixed(1));
      }
      L.me.style.display = L.halo.style.display = "";
    } else {
      L.me.style.display = L.halo.style.display = "none";
    }
    if (L.done) L.done.setAttribute("stroke-dasharray", `${(frac * 1000).toFixed(1)} 1000`);
    const showTrail = !this._track || (this._track.coverage ?? 0) < 0.98;
    L.trail.setAttribute("d", showTrail && project && this._trail.length > 1 ? polyline(this._trail.map(project)) : "");

    // Profile
    const x = frac * PROF_W;
    if (L.clip) L.clip.setAttribute("width", x.toFixed(1));
    L.cursor.setAttribute("x1", x.toFixed(1));
    L.cursor.setAttribute("x2", x.toFixed(1));
    L.cursor.style.display = this._profPts ? "" : "none";
    this._els.pGrade.textContent = a.gradient_pct != null ? `${Number(a.gradient_pct).toFixed(1)} %` : "";
    this._els.pFlag.textContent = a.remaining_m != null ? `🏁 ${(a.remaining_m / 1000).toFixed(1)} km` : "";
    this._els.bar.style.width = `${(a.progress_pct ?? 0).toFixed(1)}%`;
  }
}

if (!customElements.get("zwift-map-card")) {
  customElements.define("zwift-map-card", ZwiftMapCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "zwift-map-card",
    name: "Zwift Map",
    description: "Live Zwift route: map, elevation profile and power, readable from the bike.",
    preview: false,
  });
  console.info(`%c ZWIFT-MAP-CARD %c ${CARD_VERSION} `, "background:#f47b20;color:#fff;font-weight:700", "");
}
