/**
 * zwift-map-card — the Zwift route you are riding: map, elevation profile and
 * live numbers, readable from the bike.
 *
 *   type: custom:zwift-map-card
 *   entity: sensor.zwift_map_live
 *   zone_color_entity: light.zwift_<name>_power_zone_color   # optional
 *   ftp_entity: sensor.zwift_<name>_ftp                      # optional (or ftp: 252)
 *   layout: auto | portrait | landscape                      # default auto
 *   map_style: zwift | simple   # zwift: world map + route from ZwiftHacks (cached by
 *                               # the integration); simple: route recorded from your rides
 *   map_view: route | follow    # whole route, or zoomed on the rider
 *   follow_m: 2500              # width of the map in follow view (metres)
 *   map_rotate: 0 | 90 | 180 | 270, map_mirror: false   # simple style only
 *   show_map / show_profile / show_stats / show_segments: true
 */

const CARD_VERSION = "0.2.0";

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
    seg_in: "in",
    seg_left: "left",
    seg_at: "at",
    climb: "Climb",
    sprint: "Sprint",
    segment: "Segment",
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
    seg_in: "dans",
    seg_left: "encore",
    seg_at: "à",
    climb: "Montée",
    sprint: "Sprint",
    segment: "Segment",
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

// Segment colours, as in Zwift: KOM red, sprint green, other timed segments purple.
const SEG_COLORS = { climb: "#e8312f", sprint: "#38b24a", segment: "#8e5cf7" };
const SEG_ICONS = { climb: "⛰", sprint: "⚡", segment: "⏱" };

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
    grid-template-rows: auto auto auto auto minmax(240px, 1fr) auto;
    grid-template-areas: "head" "power" "stats" "seg" "map" "profile"; }
  .wrap.landscape { grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr);
    grid-template-rows: auto auto auto minmax(0, 1fr) auto;
    grid-template-areas: "head head" "power map" "stats map" "seg map" "profile profile"; }
  .wrap.landscape .power, .wrap.landscape .stats, .wrap.landscape .seg { align-self: start; }
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
  .map.zwift { border-radius: 14px; overflow: hidden; background: #2b4a5e; }
  .map.zwift svg { min-height: 260px; }
  .z-casing, .z-road, .z-seg, .z-lead { fill: none; stroke-linecap: round; stroke-linejoin: round;
    vector-effect: non-scaling-stroke; }
  /* No non-scaling-stroke here: it would make the dash ignore pathLength. Its
     width is set in map units by _fitZwiftView. */
  .z-done, .z-segline { fill: none; stroke-linecap: round; stroke-linejoin: round; }
  .z-casing { stroke: #15171b; stroke-opacity: .85; stroke-width: 11px; }
  .z-road { stroke: #f4f4f2; stroke-width: 5px; }
  .z-seg { stroke-width: 5px; }
  .z-lead { stroke: #f4f4f2; stroke-width: 4px; stroke-dasharray: 2 7; stroke-opacity: .9; }
  .z-done { stroke: var(--zm-done); }
  .z-me { fill: var(--zm-done); stroke: #fff; stroke-width: 4px; vector-effect: non-scaling-stroke; }
  .z-halo { fill: var(--zm-done); fill-opacity: .3; }
  .attrib { position: absolute; right: 8px; bottom: 6px; font-size: 10px; color: #fff; opacity: .75;
    text-shadow: 0 0 3px #000; pointer-events: none; }
  .pseg { opacity: .55; }
  .seg { grid-area: seg; --sc: #8e5cf7; position: relative; overflow: hidden; border-radius: 12px;
    padding: 8px 14px 10px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
    background: color-mix(in srgb, var(--sc) 22%, transparent); border-left: 6px solid var(--sc); }
  .seg .ico { font-size: clamp(20px, 5.5cqi, 30px); line-height: 1; }
  .seg .nm { font-size: clamp(18px, 5cqi, 28px); font-weight: 800; }
  .seg .info { font-size: clamp(15px, 4cqi, 22px); font-weight: 600; color: var(--zm-fg); opacity: .9;
    font-variant-numeric: tabular-nums; }
  .seg .info b { font-weight: 800; }
  .seg .sbar { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: transparent; }
  .seg .sbar > i { display: block; height: 100%; width: 0; background: var(--sc); transition: width .6s linear; }
  .seg.inside { background: color-mix(in srgb, var(--sc) 38%, transparent); }
  .pwrap { position: relative; }
  .ptags { position: absolute; inset: 0 0 auto 0; height: 0; pointer-events: none; }
  .ptag { position: absolute; top: 2px; transform: translateX(-1px); white-space: nowrap; font-size: 12px;
    font-weight: 700; padding: 1px 6px 1px 5px; border-left: 3px solid var(--tc); color: #fff;
    background: color-mix(in srgb, var(--tc) 55%, rgba(0,0,0,.55)); border-radius: 0 4px 4px 0; }
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
      map_style: "zwift",
      map_view: "route",
      follow_m: 2500,
      map_rotate: 0,
      map_mirror: false,
      show_map: true,
      show_profile: true,
      show_stats: true,
      show_segments: true,
      ...config,
    };
    this._built = false;
    this._trackKey = null;
    this._mapRoute = undefined;
    this._zmap = null;
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
      this._ro = new ResizeObserver(() => {
        this._applyLayout();
        this._fitZwiftView();
      });
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
          <div class="seg hidden"><span class="ico"></span><span class="nm"></span><span class="info"></span><div class="sbar"><i></i></div></div>
          <div class="map"><svg viewBox="0 0 ${MAP_W} ${MAP_H}" preserveAspectRatio="xMidYMid meet"></svg><div class="note hidden"></div><div class="attrib hidden">Map: ZwiftHacks</div></div>
          <div class="profile">
            <div class="plabels"><span class="g"></span><span class="f"></span></div>
            <div class="pwrap"><svg viewBox="0 0 ${PROF_W} ${PROF_H}" preserveAspectRatio="none"></svg><div class="ptags"></div></div>
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
      attrib: $(".map .attrib"),
      seg: $(".seg"),
      segIco: $(".seg .ico"),
      segNm: $(".seg .nm"),
      segInfo: $(".seg .info"),
      segBar: $(".seg .sbar > i"),
      ptags: $(".ptags"),
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
    this._renderSegmentBanner(a.segment);
    const zone = this._zoneColor(a.power_w);
    e.card.style.setProperty("--zm-zone", zone);
    e.card.style.setProperty("--zm-accent", this._config.accent_color || "#f47b20");

    // Route geometry: the Zwift-style map once per route, otherwise the
    // recorded track (reloaded when it grows).
    const routeId = a.route_id || 0;
    if (routeId !== this._mapRoute) {
      this._trail = [];
      this._mapRoute = routeId;
      this._zmap = null;
      this._trackKey = null;
      this._loadGeometry(routeId, a);
    } else if (!this._zmap && !this._loadingMap) {
      const key = `${routeId}:${a.track_version}`;
      if (key !== this._trackKey) {
        this._trackKey = key;
        this._loadTrack(routeId, a);
      }
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

  _renderSegmentBanner(seg) {
    const e = this._els;
    if (!seg || !this._config.show_segments) {
      e.seg.classList.add("hidden");
      return;
    }
    const km = (m) => `${(m / 1000).toFixed(m < 10000 ? 1 : 0)} km`;
    const len = (m) => (m < 1000 ? `${Math.round(m)} m` : km(m));
    e.seg.classList.remove("hidden");
    e.seg.classList.toggle("inside", Boolean(seg.inside));
    e.seg.style.setProperty("--sc", SEG_COLORS[seg.type] || SEG_COLORS.segment);
    e.segIco.textContent = SEG_ICONS[seg.type] || SEG_ICONS.segment;
    e.segNm.textContent = seg.name;
    const grade = seg.avg_grade != null && seg.type === "climb" ? ` ${this._t("seg_at")} ${seg.avg_grade} %` : "";
    e.segInfo.innerHTML = seg.inside
      ? `${this._t("seg_left")} <b>${len(seg.remaining_m)}</b>`
      : `${this._t("seg_in")} <b>${len(seg.distance_to_m)}</b> · ${len(seg.length_m)}${grade}`;
    e.segBar.style.width = `${seg.inside ? seg.progress_pct : 0}%`;
  }

  // Segments of the current route from the catalogue: {from_m, to_m, type, name, color}.
  _routeSegments(attrs) {
    if (!this._config.show_segments) return [];
    return (attrs.segments || []).map(([from_m, to_m, type, name]) => ({
      from_m, to_m, type, name, color: SEG_COLORS[type] || SEG_COLORS.segment,
    }));
  }

  // Coloured stretches drawn over a route path by dashing a copy of it.
  _drawSegmentLines(parent, d, length, segs, cls, extra = {}) {
    const lines = [];
    for (const s of segs) {
      const a = Math.max(0, Math.min(1, s.from_m / length)) * 1000;
      const b = Math.max(0, Math.min(1, s.to_m / length)) * 1000;
      if (b <= a) continue;
      // A dash pattern starting with a zero-length dash would leave a round-capped
      // dot at the path's start: shift the pattern with an offset instead.
      lines.push(el("path", { d, class: cls, stroke: s.color, pathLength: 1000,
        "stroke-dasharray": `${(b - a).toFixed(2)} 2000`, "stroke-dashoffset": (-a).toFixed(2), ...extra }, parent));
    }
    return lines;
  }

  // Start (white, ringed) and finish (filled) markers of each segment.
  _drawSegmentDots(parent, pathEl, totalLen, length, segs) {
    const dots = [];
    if (!pathEl || !totalLen || !length) return dots;
    for (const s of segs) {
      for (const [at, finish] of [[s.from_m, false], [s.to_m, true]]) {
        let p;
        try {
          p = pathEl.getPointAtLength(Math.min(Math.max(at / length, 0), 1) * totalLen);
        } catch (_err) {
          continue;
        }
        dots.push(el("circle", { cx: p.x.toFixed(1), cy: p.y.toFixed(1), r: 0,
          fill: finish ? s.color : "#fff", stroke: finish ? "#fff" : s.color, class: "segdot" }, parent));
      }
    }
    return dots;
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

  async _loadGeometry(routeId, attrs) {
    if (routeId && this._config.map_style !== "simple") {
      this._loadingMap = true;
      let zmap = null;
      try {
        zmap = await this._hass.callApi("GET", `zwift_map/map/${routeId}`);
      } catch (_err) {
        zmap = null;
      }
      this._loadingMap = false;
      if (routeId !== this._mapRoute) return; // the route changed meanwhile
      if (zmap && zmap.route) {
        this._zmap = zmap;
        this._drawStatic(attrs);
        return;
      }
    }
    this._trackKey = `${routeId}:${attrs.track_version}`;
    await this._loadTrack(routeId, attrs);
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
    e.mapSvg.replaceChildren();
    e.profSvg.replaceChildren();
    this._live = {};
    const zwift = Boolean(this._zmap);
    e.map.classList.toggle("zwift", zwift);
    e.attrib.classList.toggle("hidden", !zwift);
    if (zwift) this._drawZwiftMap(attrs);
    else this._drawSimpleMap(attrs);

    // ---- profile: [distance from start line (m), altitude (m)]
    const length = attrs.route_length_m || this._zmap?.route_length_m || this._track?.length_m || 0;
    let pts = [];
    let segs = this._routeSegments(attrs);
    if (zwift && this._zmap.profile?.route?.length > 1) {
      pts = this._zmap.profile.route;
      if (!segs.length && this._config.show_segments) segs = this._zmap.profile.segments || [];
    } else if (this._track) {
      pts = this._track.points.filter((p) => p[0] >= 0 && p[0] <= length).map((p) => [p[0], p[3]]);
    }
    this._drawProfile(pts, length, segs);
    this._renderLive(attrs);
  }

  _drawProfile(pts, length, segs) {
    const prof = this._els.profSvg;
    const L = this._live;
    const span = length || (pts.length ? pts[pts.length - 1][0] : 0);
    this._profSpan = span;
    if (pts.length > 1 && span) {
      let lo = Infinity, hi = -Infinity;
      for (const p of pts) {
        if (p[1] < lo) lo = p[1];
        if (p[1] > hi) hi = p[1];
      }
      const range = Math.max(hi - lo, 20);
      const py = (alt) => PROF_H - 8 - ((alt - lo) / range) * (PROF_H - 12);
      const px = (d) => (d / span) * PROF_W;
      const line = pts.map((p) => [px(p[0]), py(p[1])]);
      const area = polyline(line) + `L${PROF_W} ${PROF_H}L0 ${PROF_H}Z`;
      const defs = el("defs", {}, prof);
      const done = el("clipPath", { id: "zm-done" }, defs);
      L.clip = el("rect", { x: 0, y: 0, width: 0, height: PROF_H }, done);
      const under = el("clipPath", { id: "zm-under" }, defs);
      el("path", { d: area }, under);
      el("path", { d: area, class: "area" }, prof);
      for (const s of segs) {
        el("rect", { x: px(s.from_m), y: 0, width: Math.max(px(s.to_m) - px(s.from_m), 1), height: PROF_H,
          fill: s.color, class: "pseg", "clip-path": "url(#zm-under)" }, prof);
      }
      el("path", { d: area, class: "area-done", "clip-path": "url(#zm-done)" }, prof);
      el("path", { d: polyline(line), class: "line" }, prof);
      this._profPts = pts;
    } else {
      this._profPts = null;
    }
    this._drawProfileTags(segs, span);
    L.cursor = el("line", { y1: 0, y2: PROF_H, class: "cursor" }, prof);
  }

  // Segment names above the profile, skipping those that would overlap.
  _drawProfileTags(segs, span) {
    const box = this._els.ptags;
    box.replaceChildren();
    if (!span || !this._profPts) return;
    const width = this._els.profSvg.clientWidth || 600;
    let freeFrom = -Infinity;
    for (const s of [...segs].filter((x) => x.name).sort((a, b) => a.from_m - b.from_m)) {
      const left = (Math.max(s.from_m, 0) / span) * width;
      const w = 18 + s.name.length * 7;
      if (left < freeFrom || left + Math.min(w, 60) > width) continue;
      const tag = document.createElement("span");
      tag.className = "ptag";
      tag.textContent = `${SEG_ICONS[s.type] || ""} ${s.name}`.trim();
      tag.style.setProperty("--tc", s.color);
      tag.style.left = `${Math.min(left, width - w)}px`;
      box.appendChild(tag);
      freeFrom = left + w + 6;
    }
  }

  _drawSimpleMap(attrs) {
    const e = this._els;
    const map = e.mapSvg;
    const track = this._track;
    map.setAttribute("viewBox", `0 0 ${MAP_W} ${MAP_H}`);
    map.setAttribute("preserveAspectRatio", "xMidYMid meet");
    if (track) {
      const pts = track.points.map((p) => [p[1], p[2]]);
      this._project = this._projector(pts);
      el("path", { d: polyline(pts.map(this._project)), class: "road", "stroke-width": 26 }, map);
      // Distance-proportional dash: points are evenly spaced along the road.
      const onRoute = track.points.filter((p) => p[0] >= 0).map((p) => this._project([p[1], p[2]]));
      this._live.done = el("path", { d: polyline(onRoute), class: "done", "stroke-width": 14, pathLength: 1000, "stroke-dasharray": "0 1000" }, map);
      const segs = this._routeSegments(attrs);
      const len = attrs.route_length_m || track.length_m;
      if (segs.length && len) {
        this._drawSegmentLines(map, polyline(onRoute), len, segs, "segline",
          { fill: "none", "stroke-width": 9, "stroke-linecap": "round" });
        let total = 0;
        try { total = this._live.done.getTotalLength(); } catch (_err) { total = 0; }
        for (const dot of this._drawSegmentDots(map, this._live.done, total, len, segs)) {
          dot.setAttribute("r", 9);
          dot.setAttribute("stroke-width", 4);
        }
      }
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
  }

  // World map + route from ZwiftHacks, in its world coordinates (centimetres).
  _drawZwiftMap(attrs) {
    const e = this._els;
    const map = e.mapSvg;
    const z = this._zmap;
    const L = this._live;
    e.note.classList.add("hidden");
    map.setAttribute("preserveAspectRatio", "xMidYMid slice");
    const bg = z.background;
    if (bg && bg.url) {
      el("image", { href: bg.url, x: bg.x, y: bg.y, width: bg.width, height: bg.height,
        preserveAspectRatio: "none", opacity: bg.opacity ?? 1 }, map);
    }
    if (z.leadin) el("path", { d: z.leadin, class: "z-lead" }, map);
    el("path", { d: z.route, class: "z-casing" }, map);
    L.route = el("path", { d: z.route, class: "z-road" }, map);
    L.leadPath = z.leadin ? el("path", { d: z.leadin, fill: "none", stroke: "none" }, map) : null;
    try {
      this._routeLen = L.route.getTotalLength();
      this._leadLen = L.leadPath ? L.leadPath.getTotalLength() : 0;
    } catch (_err) {
      this._routeLen = this._leadLen = 0;
    }
    const segs = this._routeSegments(attrs);
    const length = attrs.route_length_m || 0;
    if (!segs.length && this._config.show_segments) {
      for (const s of z.segments || []) el("path", { d: s.d, class: "z-seg", stroke: s.color }, map);
    }
    L.done = el("path", { d: z.route, class: "z-done", pathLength: 1000, "stroke-dasharray": "0 1000" }, map);
    L.segLines = length ? this._drawSegmentLines(map, z.route, length, segs, "z-segline") : [];
    L.segDots = this._drawSegmentDots(map, L.route, this._routeLen, length, segs);
    L.halo = el("circle", { r: 0, class: "z-halo" }, map);
    L.me = el("circle", { r: 0, class: "z-me" }, map);
    this._fitZwiftView();
  }

  // Fit the route's view to the map box (no letterboxing), or follow the rider.
  _fitZwiftView(center) {
    if (!this._zmap || !this._els) return;
    const svg = this._els.mapSvg;
    const w = svg.clientWidth || 1;
    const h = svg.clientHeight || 1;
    const aspect = w / h;
    let vx, vy, vw, vh;
    if (this._config.map_view === "follow" && (center || this._lastPos)) {
      const [cx, cy] = center || this._lastPos;
      vw = Number(this._config.follow_m) * 100;
      vh = vw / aspect;
      vx = cx - vw / 2;
      vy = cy - vh / 2;
    } else {
      const [x, y, tw, th] = this._zmap.view;
      const pad = 0.06;
      vw = tw * (1 + 2 * pad);
      vh = th * (1 + 2 * pad);
      if (vw / vh > aspect) vh = vw / aspect;
      else vw = vh * aspect;
      vx = x + tw / 2 - vw / 2;
      vy = y + th / 2 - vh / 2;
    }
    svg.setAttribute("viewBox", `${vx.toFixed(0)} ${vy.toFixed(0)} ${vw.toFixed(0)} ${vh.toFixed(0)}`);
    // Marker size in map units: constant on screen.
    const unit = vw / w;
    if (this._live?.me) {
      this._live.me.setAttribute("r", (11 * unit).toFixed(0));
      this._live.halo.setAttribute("r", (24 * unit).toFixed(0));
      this._live.done?.setAttribute("stroke-width", (7 * unit).toFixed(0));
      for (const line of this._live.segLines || []) line.setAttribute("stroke-width", (5 * unit).toFixed(0));
      for (const dot of this._live.segDots || []) {
        dot.setAttribute("r", (6 * unit).toFixed(0));
        dot.setAttribute("stroke-width", (3 * unit).toFixed(0));
      }
    }
  }

  _renderLive(a) {
    const L = this._live;
    if (!L || !L.me) return;
    const length = a.route_length_m || this._track?.length_m || 0;
    const along = a.lap_distance_m != null ? Math.max(0, a.lap_distance_m) : 0;
    const frac = length ? Math.min(along / length, 1) : 0;

    if (this._zmap) {
      // Rider placed by distance along the route (or the lead-in) path.
      let pos = null;
      try {
        if (a.route_distance_m != null && a.route_distance_m < 0 && L.leadPath && this._leadLen) {
          const leadM = a.lead_in_m || 1;
          const f = Math.min(Math.max((leadM + a.route_distance_m) / leadM, 0), 1);
          pos = L.leadPath.getPointAtLength(f * this._leadLen);
        } else if (this._routeLen) {
          pos = L.route.getPointAtLength(frac * this._routeLen);
        }
      } catch (_err) {
        pos = null;
      }
      if (pos) {
        this._lastPos = [pos.x, pos.y];
        for (const c of [L.me, L.halo]) {
          c.setAttribute("cx", pos.x.toFixed(0));
          c.setAttribute("cy", pos.y.toFixed(0));
        }
        if (this._config.map_view === "follow") this._fitZwiftView(this._lastPos);
      }
      L.me.style.display = L.halo.style.display = pos ? "" : "none";
      L.done.setAttribute("stroke-dasharray", `${(frac * 1000).toFixed(1)} 1000`);
    } else {
      // Simple style: projection from the recorded track, or the live trail.
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
    }

    // Profile
    const span = this._profSpan || length;
    const x = span ? Math.min(Math.max(along, 0) / span, 1) * PROF_W : 0;
    if (L.clip) L.clip.setAttribute("width", x.toFixed(1));
    if (L.cursor) {
      L.cursor.setAttribute("x1", x.toFixed(1));
      L.cursor.setAttribute("x2", x.toFixed(1));
      L.cursor.style.display = this._profPts ? "" : "none";
    }
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
