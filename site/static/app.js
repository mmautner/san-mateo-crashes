import * as C from "./core.js";

const BASE = document.documentElement.dataset.base; // "/san-mateo-crashes/"
const CFG = { service: document.documentElement.dataset.cityService, calming: document.documentElement.dataset.cityCalming };
const radiusWordsFor = (miles) => (C.RADII.find((r) => r.miles === miles) || { words: `${miles} mile` }).words;
const $ = (s, el = document) => el.querySelector(s);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

async function loadData() {
  const v = document.documentElement.dataset.version || "";
  const [crashes, ints, plans] = await Promise.all([
    fetch(`${BASE}data/crashes.json?v=${v}`).then((r) => r.json()),
    fetch(`${BASE}data/intersections.json?v=${v}`).then((r) => r.json()),
    fetch(`${BASE}data/plans.json?v=${v}`).then((r) => r.json()).catch(() => null),
  ]);
  const data = C.prepare(crashes, ints);
  data.plans = C.preparePlans(plans);
  return data;
}

// ------------------------------------------------------------------ search
function setupSearch(data) {
  const box = $(".cx-search");
  if (!box) return;
  const input = $("input", box), list = $(".cx-options", box), status = $(".cx-status", box);
  let items = [], active = -1;
  const go = (i) => { location.href = `${BASE}${i.id}/`; };
  const render = () => {
    list.innerHTML = items.length
      ? items.map((i, k) => `<li role="option" id="cx-opt-${k}" aria-selected="${k === active}">${esc(i.label)}</li>`).join("")
      : `<li class="cx-empty" role="option" aria-disabled="true">No San Mateo intersection matches. Try a street name, like “Aragon”.</li>`;
    list.hidden = !input.value.trim();
    input.setAttribute("aria-expanded", String(!list.hidden));
    input.setAttribute("aria-activedescendant", active >= 0 ? `cx-opt-${active}` : "");
  };
  input.addEventListener("input", () => { items = C.search(data, input.value); active = items.length ? 0 : -1; render(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!items.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      render();
    } else if (e.key === "Enter" && active >= 0) { e.preventDefault(); go(items[active]); }
    else if (e.key === "Escape") { list.hidden = true; input.setAttribute("aria-expanded", "false"); }
  });
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[id]");
    if (li) { e.preventDefault(); go(items[+li.id.slice(7)]); }
  });
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 150));

  const locate = $(".cx-locate", box);
  if (locate && "geolocation" in navigator) {
    locate.hidden = false;
    locate.addEventListener("click", () => {
      status.textContent = "Finding the nearest intersection…";
      navigator.geolocation.getCurrentPosition((pos) => {
        const { int, meters } = C.nearestIntersection(data, pos.coords.longitude, pos.coords.latitude);
        if (meters > 1500) { status.textContent = "You don't seem to be in San Mateo. Type a street name instead."; return; }
        go(int);
      }, () => { status.textContent = "Couldn't get your location. Type a street name instead."; },
      { enableHighAccuracy: false, timeout: 10000 });
    });
  }
}

const POPUP_ROWS = new Set(["Type of crash", "Cause the officer recorded"]);
function detailsHtml(c, compact = false) {
  const rows = C.detailRows(c).filter(([k]) => !compact || POPUP_ROWS.has(k));
  if (!rows.length) return "";
  return `<dl class="cx-dl">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
}

// ------------------------------------------------------------------ intersection page
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

// The site's tokens are oklch(); MapLibre and canvas readers need plain rgb.
const _px = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
function cssColor(name) {
  _px.clearRect(0, 0, 1, 1);
  _px.fillStyle = "#000";
  _px.fillStyle = cssVar(name);
  _px.fillRect(0, 0, 1, 1);
  const [r, g, b] = _px.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}

function setupIntersection(data, page) {
  const int = data.byId.get(page.dataset.id);
  const meta = data.meta;
  let s = C.readSettings(location.search, meta);

  // controls
  const rSel = $("#cx-radius"), y0Sel = $("#cx-from"), y1Sel = $("#cx-to");
  rSel.innerHTML = C.RADII.map((r) => `<option value="${r.miles}">${r.short}</option>`).join("");
  const years = []; for (let y = meta.years[0]; y <= meta.years[1]; y++) years.push(y);
  y0Sel.innerHTML = y1Sel.innerHTML = years.map((y) => `<option>${y}</option>`).join("");
  const syncControls = () => { rSel.value = String(s.miles); y0Sel.value = String(s.y0); y1Sel.value = String(s.y1); };
  syncControls();
  const onChange = () => {
    s = { miles: +rSel.value, y0: +y0Sel.value, y1: +y1Sel.value };
    if (s.y0 > s.y1) { if (document.activeElement === y0Sel) s.y1 = s.y0; else s.y0 = s.y1; syncControls(); }
    history.replaceState(null, "", `${location.pathname}${C.writeSettings(s, meta)}`);
    update();
  };
  [rSel, y0Sel, y1Sel].forEach((el) => el.addEventListener("change", onChange));

  let current = { text: "", near: [], miles: s.miles };
  const distCache = new Map();
  function update() {
    const near = C.nearby(data, int.px, int.py, s.miles, s.y0, s.y1);
    const t = C.tally(near);
    const key = `${s.miles}|${s.y0}|${s.y1}`;
    if (!distCache.has(key)) distCache.set(key, C.distribution(data, s.miles, s.y0, s.y1));
    current.miles = s.miles;
    const text = C.headline(int.label, t, s, meta.years[1]);
    $("#cx-headline").textContent = text;
    $("#cx-context").textContent = C.context(t.n, distCache.get(key), s);
    $("#cx-gap").textContent = C.gapNote(meta, s.y0, s.y1);
    $("#cx-noinjury").textContent = C.noInjurySentence(C.noInjuryCount(data, int.px, int.py, s.miles, s.y0, s.y1), s);
    const pat = C.patterns(near);
    const sentence = C.patternSentence(pat);
    $("#cx-pattern").textContent = sentence;
    renderPatterns(pat);
    const ctx = C.planContext(data.plans, int, s.miles);
    renderPlan(ctx);
    current = { text, near, sentence, plan: C.planSentence(data.plans, ctx, s) };
    renderList(near);
    updateCouncil();
    map.update(near, s.miles);
  }

  function renderPatterns(p) {
    const box = $("#cx-patterns");
    if (p.n < C.MIN_PATTERN_CRASHES) {
      box.innerHTML = `<h2>What the police reports say</h2><p class="cx-meta">Too few crashes here to show a pattern. Tap any crash below for its details.</p>`;
      return;
    }
    const li = (rows) => rows.map(([v, k]) => `<li>${esc(v)} <span class="cx-count">${k}</span></li>`).join("");
    const facts = [`<li>After dark: <strong>${p.dark}</strong> of ${p.n} crashes</li>`];
    if (p.walking) facts.push(`<li>Someone walking was hit: <strong>${p.walking}</strong> crashes; in ${p.crosswalk} of them the person was in a crosswalk</li>`);
    if (p.hitrun) facts.push(`<li>Hit and run: <strong>${p.hitrun}</strong> crashes</li>`);
    box.innerHTML = `<h2>What the police reports say</h2>
      <p class="cx-meta">From the ${p.n} crashes in which someone was hurt and no one died.</p>
      <div class="cx-pat-grid">
        <div><h3>Cause the officer recorded</h3><ol class="cx-rank">${li(p.causes)}</ol></div>
        <div><h3>Most at fault, per the officer</h3><ol class="cx-rank">${li(p.who)}</ol></div>
        <div><h3>Type of crash</h3><ol class="cx-rank">${li(p.types)}</ol></div>
      </div>
      <ul class="cx-facts">${facts.join("")}</ul>
      <p class="cx-meta">Causes and fault are the officer's judgment at the scene, not a court finding.</p>`;
  }

  function projectHtml(planId, n) {
    const pr = data.plans.projects[planId]?.[String(n)];
    if (!pr) return "";
    const list = (xs) => `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    const covers = [...data.plans.points, ...data.plans.segments].filter((x) => x.plan === planId && x.project === n).map((x) => x.name);
    return `<div class="cx-proposals">`
      + (covers.length > 1 ? `<p class="cx-meta">The plan proposes one project covering ${esc(covers.join("; "))}.</p>` : "")
      + (pr.sooner.length ? `<h4>Proposed sooner (lower cost)</h4>${list(pr.sooner)}` : "")
      + (pr.later.length ? `<h4>Proposed later (higher cost)</h4>${list(pr.later)}` : "")
      + (pr.underway ? `<p class="cx-meta">Already underway when the plan was adopted: ${esc(pr.underway)}.</p>` : "")
      + `<p class="cx-meta">Summarized from the plan, page ${pr.page}.</p></div>`;
  }
  function renderPlan(ctx) {
    const box = $("#cx-plan");
    if (!ctx) { box.hidden = true; return; }
    const lrsp = data.plans.plans.get("lrsp");
    const year = lrsp.adopted.slice(0, 4);
    const nInts = data.plans.points.filter((p) => p.plan === "lrsp").length;
    const nSegs = data.plans.segments.filter((x) => x.plan === "lrsp").length;
    const planLink = `<a href="${esc(lrsp.url)}">${esc(lrsp.title)}</a>`;
    const parts = [];
    for (const p of ctx.own) {
      parts.push(`<p class="cx-plan-lead"><strong>This intersection is #${p.rank} of ${nInts} priority intersections</strong> in the city's ${year} ${planLink} (Tier ${p.tier}).</p>`);
      if (p.status) parts.push(`<p>Status: ${esc(p.status.text)}, according to the <a href="${esc(p.status.source)}">city's Transportation Safety page</a> (checked ${C.longDate(p.status.checked)}).</p>`);
      if (p.project_url) parts.push(`<p><a href="${esc(p.project_url)}">The city's project page</a> has the current status.</p>`);
      if (p.project) parts.push(projectHtml(p.plan, p.project));
    }
    for (const g of ctx.onSegments) {
      parts.push(`<p class="cx-plan-lead"><strong>${esc(g.name)}</strong> is #${g.rank} of ${nSegs} priority street segments in the city's ${year} ${planLink}.</p>`);
      if (g.project) parts.push(projectHtml(g.plan, g.project));
    }
    const near = [...ctx.nearPoints.map((p) => {
      const name = p.id ? `<a href="${BASE}${esc(p.id)}/">${esc(p.name)}</a>` : esc(p.name);
      return `<li>#${p.rank} ${name} <span class="cx-count">intersection, Tier ${p.tier}</span></li>`;
    }), ...ctx.nearSegments.map((g) => `<li>#${g.rank} ${esc(g.name)} <span class="cx-count">street segment</span></li>`)];
    if (near.length) {
      parts.push(`<p>${ctx.own.length || ctx.onSegments.length ? "Also within" : "Within"} ${esc(radiusWordsFor(current.miles))}, the plan lists:</p><ul class="cx-rank">${near.join("")}</ul>`);
    }
    if (!parts.length) {
      parts.push(`<p>The city's ${year} ${planLink} doesn't list this intersection among its ${nInts} priority intersections or ${nSegs} priority street segments, and none are within ${esc(radiusWordsFor(current.miles))}.</p>`);
    }
    parts.push(`<p class="cx-meta">${esc(lrsp.method)}</p>`);
    parts.push(`<p class="cx-ask">Ask the city about this corner: <a href="${CFG.service}">report a concern</a> or <a href="${CFG.calming}">request a traffic calming study</a>.</p>`);
    box.innerHTML = `<h2>What the city has planned</h2>${parts.join("")}`;
    box.hidden = false;
  }

  // list
  const LIST_STEP = 50;
  let shown = LIST_STEP;
  function renderList(near) {
    const rows = near.slice(0, shown).map((c, i) => {
      const mode = c.killed ? "killed" : C.MODES[c.mode].key;
      const dot = c.killed ? `<span class="cx-key cx-key-killed" aria-hidden="true"></span>`
        : c.mode === "v" ? `<span class="cx-key cx-key-ring" aria-hidden="true"></span>`
        : `<span class="cx-key" style="background:var(--${mode})" aria-hidden="true"></span>`;
      const who = c.killed ? C.deathLine(c.people) : C.describePeople(c.people);
      const whoText = cap(who);
      const where = c.killed ? "" : `${esc(c.place || "Location from police report")}${c.approx ? " (approximate)" : ""}`;
      const head = `<span class="cx-date">${C.longDate(c.date)}</span>`
        + `<span class="cx-where">${where}</span><span class="cx-who">${dot}${esc(whoText)}</span>`;
      if (c.killed) return `<li class="cx-death"><div class="cx-row">${head}</div></li>`;
      return `<li id="cx-c-${i}"><details><summary class="cx-row">${head}</summary>${detailsHtml(c)}</details></li>`;
    });
    $("#cx-list").innerHTML = rows.join("");
    $("#cx-list-count").textContent = near.length
      ? `${near.length} ${near.length === 1 ? "crash" : "crashes"} in which someone was hurt, newest first.`
      : "No crashes in which someone was hurt.";
    const more = $("#cx-more");
    more.hidden = near.length <= shown;
    more.textContent = `Show ${Math.min(LIST_STEP, near.length - shown)} more`;
  }
  $("#cx-more").addEventListener("click", () => { shown += LIST_STEP; renderList(current.near); });
  // "Full details" in a map popup opens that crash in the list
  $("#cx-map").addEventListener("click", (e) => {
    const b = e.target.closest(".cx-goto");
    if (!b) return;
    const i = +b.dataset.i;
    if (i >= shown) { shown = Math.ceil((i + 1) / LIST_STEP) * LIST_STEP; renderList(current.near); }
    const li = $(`#cx-c-${i}`);
    li.querySelector("details").open = true;
    li.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    li.querySelector("summary").focus({ preventScroll: true });
  });

  // share
  const shareBtn = $("#cx-share");
  shareBtn.addEventListener("click", async () => {
    const url = location.href;
    const coarse = matchMedia("(pointer: coarse)").matches;
    if (navigator.share && coarse) {
      try { await navigator.share({ title: `Crashes near ${int.label}`, text: current.text, url }); } catch { /* cancelled */ }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      shareBtn.textContent = "Link copied";
    } catch {
      prompt("Copy this link:", url);
    }
    setTimeout(() => { shareBtn.textContent = "Copy link"; }, 2500);
  });
  if (navigator.share && matchMedia("(pointer: coarse)").matches) shareBtn.textContent = "Share";

  // council
  let council = null;
  fetch(`${BASE}council.json?v=${document.documentElement.dataset.version}`).then((r) => r.json()).then((c) => { council = c; updateCouncil(); });
  function updateCouncil() {
    const box = $("#cx-council");
    if (!council || !box) return;
    const m = council.members[String(int.district)];
    if (!m) { box.hidden = true; return; }
    const formal = m.salutation;
    const body = `Dear ${formal},\n\n${current.text}${current.sentence ? ` ${current.sentence}` : ""}${current.plan ? ` ${current.plan}` : ""}\n\n${location.href}\n\n\n\nWhat is the city planning for this intersection?\n`;
    const href = `mailto:${m.email}?subject=${encodeURIComponent(`Crashes near ${int.label}`)}&body=${encodeURIComponent(body)}`;
    box.innerHTML = `<p>${esc(int.label)} is in City Council District ${int.district}, represented by ${esc(m.title)} ${esc(m.name)}.</p>`
      + `<a class="cx-btn cx-btn-primary" href="${esc(href)}">Email ${esc(formal)}</a>`;
    box.hidden = false;
  }

  // map
  const map = createMap(int, $("#cx-map"));
  update();
}

// ------------------------------------------------------------------ map
function createMap(int, el) {
  let m = null, pending = null, ready = false;
  const styleUrl = () => `https://tiles.openfreemap.org/styles/${document.documentElement.dataset.theme === "light" ? "positron" : "dark"}`;

  const circle = (miles) => {
    const pts = [], r = miles * 1609.344;
    for (let k = 0; k <= 64; k++) {
      const a = (k / 64) * 2 * Math.PI;
      pts.push([int.lon + (r * Math.cos(a)) / (111320 * Math.cos((int.lat * Math.PI) / 180)), int.lat + (r * Math.sin(a)) / 110574]);
    }
    return { type: "Feature", geometry: { type: "Polygon", coordinates: [pts] } };
  };

  // crashes at the exact same spot are fanned out a few meters so each shows
  const features = (near) => {
    const seen = new Map();
    return near.map((c, i) => {
      const k = `${c.lon},${c.lat}`, n = seen.get(k) || 0;
      seen.set(k, n + 1);
      const a = n * 2.4, d = n ? 4 + 3 * Math.sqrt(n) : 0;
      const lon = c.lon + (d * Math.cos(a)) / 88000, lat = c.lat + (d * Math.sin(a)) / 110574;
      const killedMode = c.killed ? C.MODES[c.people.find((p) => p[1] === "k")[0]] : null;
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [lon, lat] },
        properties: {
          kind: c.killed ? "killed" : C.MODES[c.mode].key,
          label: c.killed ? `Killed · ${C.monthYear(c.date)} · ${killedMode.many}` : "",
          html: `<strong>${C.longDate(c.date)}</strong><br>${c.killed ? "" : esc(c.place || "") + "<br>"}${esc(c.killed
            ? C.deathLine(c.people) : cap(C.describePeople(c.people)))}${detailsHtml(c, true)}`
            + (c.killed ? "" : `<button type="button" class="cx-goto" data-i="${i}">Full details</button>`),
        },
      };
    });
  };

  function paint(near, miles) {
    const src = m.getSource("crashes");
    if (!src) return;
    src.setData({ type: "FeatureCollection", features: features(near) });
    m.getSource("radius").setData(circle(miles));
    const r = miles * 1609.344, dLon = r / (111320 * Math.cos((int.lat * Math.PI) / 180)), dLat = r / 110574;
    m.fitBounds([[int.lon - dLon, int.lat - dLat], [int.lon + dLon, int.lat + dLat]], { padding: { top: 20, right: 20, bottom: 44, left: 20 }, animate: ready });
  }

  function addLayers() {
    const col = (v) => cssColor(v);
    m.addSource("radius", { type: "geojson", data: circle(0.25) });
    m.addSource("crashes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    m.addSource("center", { type: "geojson", data: { type: "Feature", geometry: { type: "Point", coordinates: [int.lon, int.lat] } } });
    m.addLayer({ id: "radius-fill", type: "fill", source: "radius", paint: { "fill-color": col("--accent"), "fill-opacity": 0.06 } });
    m.addLayer({ id: "radius-line", type: "line", source: "radius", paint: { "line-color": col("--accent"), "line-width": 1.5, "line-dasharray": [2, 2] } });
    const surface = col("--bg");
    m.addLayer({ id: "vehicle", type: "circle", source: "crashes", filter: ["==", ["get", "kind"], "vehicle"],
      paint: { "circle-radius": 4.5, "circle-color": surface, "circle-stroke-color": col("--vehicle"), "circle-stroke-width": 2 } });
    m.addLayer({ id: "vulnerable", type: "circle", source: "crashes", filter: ["in", ["get", "kind"], ["literal", ["walk", "bike", "scooter"]]],
      paint: { "circle-radius": 6, "circle-stroke-color": surface, "circle-stroke-width": 2,
        "circle-color": ["match", ["get", "kind"], "walk", col("--walk"), "bike", col("--bike"), col("--scooter")] } });
    m.addLayer({ id: "center", type: "circle", source: "center",
      paint: { "circle-radius": 5, "circle-color": surface, "circle-stroke-color": col("--accent"), "circle-stroke-width": 3 } });
    m.addLayer({ id: "killed", type: "symbol", source: "crashes", filter: ["==", ["get", "kind"], "killed"],
      layout: { "icon-image": "killed", "icon-allow-overlap": true, "text-field": ["get", "label"], "text-size": 12,
        "text-offset": [0, 1.3], "text-anchor": "top", "text-font": ["Noto Sans Bold"], "text-optional": true },
      paint: { "text-color": col("--text"), "text-halo-color": surface, "text-halo-width": 2 } });
  }

  function addIcon() {
    const size = 22, c = document.createElement("canvas");
    c.width = c.height = size * 2;
    const g = c.getContext("2d");
    g.scale(2, 2);
    g.translate(size / 2, size / 2);
    g.rotate(Math.PI / 4);
    g.fillStyle = cssColor("--bg"); g.fillRect(-7.5, -7.5, 15, 15);
    g.fillStyle = cssColor("--killed"); g.fillRect(-5.5, -5.5, 11, 11);
    if (m.hasImage("killed")) m.removeImage("killed");
    m.addImage("killed", g.getImageData(0, 0, size * 2, size * 2), { pixelRatio: 2 });
  }

  function init() {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.css";
    document.head.append(css);
    const js = document.createElement("script");
    js.src = "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.js";
    js.onload = () => {
      m = new maplibregl.Map({ container: el, style: styleUrl(), center: [int.lon, int.lat], zoom: 15,
        attributionControl: { compact: true }, cooperativeGestures: true, dragRotate: false, pitchWithRotate: false });
      if (new URLSearchParams(location.search).has("debug")) window.__cxmap = m;
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.on("style.load", () => {
        addIcon(); addLayers();
        if (pending) paint(...pending);
        ready = true;
      });
      const popup = new maplibregl.Popup({ closeButton: false, offset: 10 });
      for (const layer of ["vehicle", "vulnerable", "killed"]) {
        m.on("click", layer, (e) => popup.setLngLat(e.features[0].geometry.coordinates).setHTML(e.features[0].properties.html).addTo(m));
        m.on("mouseenter", layer, () => { m.getCanvas().style.cursor = "pointer"; });
        m.on("mouseleave", layer, () => { m.getCanvas().style.cursor = ""; });
      }
      // follow the site's light/dark toggle
      new MutationObserver(() => { ready = false; m.setStyle(styleUrl()); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    };
    document.head.append(js);
  }
  init();

  return {
    update(near, miles) {
      pending = [near, miles];
      if (m && m.getSource && m.getSource("crashes")) paint(near, miles);
    },
  };
}

// ------------------------------------------------------------------ boot
loadData().then((data) => {
  setupSearch(data);
  const page = $(".cx-intersection");
  if (page) setupIntersection(data, page);
}).catch((e) => {
  const s = $(".cx-status") || $("#cx-context");
  if (s) s.textContent = "The crash data didn't load. Check your connection and reload the page.";
  console.error(e);
});
