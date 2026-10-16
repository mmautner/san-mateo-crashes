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
  rSel.innerHTML = C.RADII.map((r) => `<option value="${r.miles}">${r.short} · ${r.menu}</option>`).join("");
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
    $("#cx-at").textContent = C.atIntersectionSentence(C.atIntersection(data, int, s), t.n);
    $("#cx-legend-circle").textContent = cap(radiusWordsFor(s.miles));
    $("#cx-context").textContent = C.context(t.n, distCache.get(key), s);

    const noInjury = C.noInjurySentence(C.noInjuryCount(data, int.px, int.py, s.miles, s.y0, s.y1), s);
    const pat = C.patterns(near);
    const sentence = C.patternSentence(pat);
    renderPatterns(pat, sentence, noInjury);
    renderYears(s);
    // the plan section is supplementary: a problem there must not stop the rest of the page
    let planLine = "";
    try {
      const ctx = C.planContext(data.plans, int, s.miles);
      const items = C.planItems(data.plans, ctx);
      renderPlan(ctx, items);
      planLine = [C.planSentence(data.plans, ctx, s), C.actionSentences(items)].filter(Boolean).join(" ");
    } catch (err) {
      console.error(err);
      $("#cx-plan").hidden = true;
    }
    current = { text, near, sentence, plan: planLine };
    showAll = false;
    renderList(near);
    updateCouncil();
    map.update(near, s.miles);
  }

  // people hurt each year within the chosen distance; the chosen years are solid,
  // years with missing police reports are striped and footnoted
  const gaps = C.gapYears(meta);
  function renderYears(s) {
    const rows = C.byYear(data, int.px, int.py, s.miles);
    const max = Math.max(1, ...rows.map((r) => r.n));
    const anyGap = rows.some((r) => gaps.has(r.year));
    const bars = rows.map((r) => {
      const cls = ["cx-bar", r.year >= s.y0 && r.year <= s.y1 ? "is-in" : "", gaps.has(r.year) ? "is-gap" : ""].join(" ");
      const h = r.n ? Math.max(3, (r.n / max) * 100) : 0;
      return `<div class="${cls}" title="${r.year}: ${r.n} ${r.n === 1 ? "person" : "people"} hurt${gaps.has(r.year) ? " (police reports missing for part of the year)" : ""}">`
        + `<span class="cx-bar-plot"><span class="cx-bar-fill" style="height:${h}%"><span class="cx-bar-n">${r.n}</span></span></span>`
        + `<span class="cx-bar-y">’${String(r.year).slice(2)}${gaps.has(r.year) ? "*" : ""}</span></div>`;
    }).join("");
    const g = meta.gaps[0];
    $("#cx-years").innerHTML = `<h3 class="cx-years-title">People hurt each year within ${esc(radiusWordsFor(s.miles))}</h3>`
      + `<div class="cx-bars" aria-hidden="true">${bars}</div>`
      + `<ul class="cx-sr">${rows.map((r) => `<li>${r.year}: ${r.n}</li>`).join("")}</ul>`
      + `<p class="cx-meta cx-years-key"><span class="cx-swatch" aria-hidden="true"></span>The years counted above${s.y0 === meta.years[0] && s.y1 === meta.years[1] ? "" : `; gray bars are other years`}.</p>`
      + (anyGap ? `<p class="cx-meta">* ${esc(g.agency)} reports from ${C.monthYear(g.from)} through ${C.monthYear(g.to)} are missing from the state's data, so these years count too few.</p>` : "");
  }

  function renderPatterns(p, sentence, noInjury) {
    const box = $("#cx-patterns");
    const tail = noInjury ? `<p class="cx-noinjury">${esc(noInjury)}</p>` : "";
    if (p.n < C.MIN_PATTERN_CRASHES) {
      box.innerHTML = `<h2>What the police reports say</h2><p class="cx-meta">Too few crashes here to show a pattern. Tap any crash below for its details.</p>${tail}`;
      return;
    }
    const li = (rows) => rows.map(([v, k]) => `<li>${esc(v)} <span class="cx-count">${k}</span></li>`).join("");
    const facts = [`<li>After dark: <strong>${p.dark}</strong> of ${p.n} crashes</li>`];
    if (p.walking) facts.push(`<li>Someone walking was hit: <strong>${p.walking}</strong> crashes; in ${p.crosswalk} of them the person was in a crosswalk</li>`);
    if (p.hitrun) facts.push(`<li>Hit and run: <strong>${p.hitrun}</strong> crashes</li>`);
    box.innerHTML = `<h2>What the police reports say</h2>
      ${sentence ? `<p class="cx-pattern">${esc(sentence)}</p>` : ""}
      <p class="cx-meta">From the ${p.n} crashes in which someone was hurt and no one died.</p>
      <div class="cx-pat-grid">
        <div><h3>Cause the officer recorded</h3><ol class="cx-rank">${li(p.causes)}</ol></div>
        <div><h3>Most at fault, per the officer</h3><ol class="cx-rank">${li(p.who)}</ol></div>
        <div><h3>Type of crash</h3><ol class="cx-rank">${li(p.types)}</ol></div>
      </div>
      <ul class="cx-facts">${facts.join("")}</ul>
      <p class="cx-meta">Causes and fault are the officer's judgment at the scene, not a court finding.</p>${tail}`;
  }

  const listHtml = (xs) => `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  // "a bike boulevard (a calmer street ...)" -> "Bike boulevard"; the definition is shown once, below the list
  const bikeway = (f) => { const t = f.replace(/^an? /, "").replace(/ \(.*\)$/, ""); return t.charAt(0).toUpperCase() + t.slice(1); };
  const BIKE_GLOSSARY = { "Bike boulevard": "A bike boulevard is a calmer street with signs and markings for bikes, often with traffic calming." };
  const MAX_NEAR = 5;
  const listLabel = (plan) => { const t = plan.list_label || "The plan"; return t.charAt(0).toLowerCase() + t.slice(1); };

  function proposalsHtml(plan, e) {
    // ranked plans keep proposals in a shared projects table; the others carry them inline
    const inline = e.sooner || e.other;
    const src = inline ? e : data.plans.projects[plan.id]?.[String(e.project)];
    if (!src) return "";
    const pr = { ...src, sooner: src.sooner || [], later: src.later || [], other: src.other || [] };
    const covers = inline ? [] : [...data.plans.points, ...data.plans.segments]
      .filter((x) => x.plan === plan.id && x.project === e.project).map((x) => x.name);
    const source = inline
      ? `<a href="${esc(plan.pdf)}#page=${e.page}">${esc(listLabel(plan))}, page ${e.page}</a>`
      : `<a href="${esc(plan.pdf)}#page=${pr.page}">the plan, page ${pr.page}</a>`;
    return `<div class="cx-proposals">`
      + (covers.length > 1 ? `<p class="cx-meta">One project in the plan covers ${esc(covers.join("; "))}.</p>` : "")
      + (pr.sooner.length ? `<h4>${inline ? "Short term" : "Sooner, lower cost"}</h4>${listHtml(pr.sooner)}` : "")
      + (pr.later.length ? `<h4>${inline ? "Medium term" : "Later, higher cost"}</h4>${listHtml(pr.later)}` : "")
      + (pr.other.length ? `<h4>Recommended</h4>${listHtml(pr.other)}` : "")
      + (pr.underway ? `<p class="cx-meta">Already underway when the plan was adopted: ${esc(pr.underway)}.</p>` : "")
      + `<p class="cx-meta">${inline ? "Full wording" : "Summarized from"}: ${source}.</p></div>`;
  }

  // one row of a "nearby" list: the place, then a short description under it
  function nearRow(plan, x, nInts, nSegs) {
    const name = x.id ? `<a href="${BASE}${esc(x.id)}/">${esc(x.name)}</a>` : esc(x.name);
    let meta = "";
    if (x.rank) meta = x.line ? `#${x.rank} of ${nSegs} priority street segments` : `#${x.rank} of ${nInts} priority intersections`;
    else if (x.facility) meta = `${bikeway(x.facility)} · ${x.priority} priority`;
    else {
      const all = [...(x.sooner || []), ...(x.later || []), ...(x.other || [])];
      meta = all.length ? `${all[0]}${all.length > 1 ? ` and ${all.length - 1} more ${all.length === 2 ? "change" : "changes"}` : ""}` : "";
    }
    return `<li>${name}${meta ? `<span class="cx-near-meta">${esc(meta)}</span>` : ""}</li>`;
  }
  function nearList(plan, items, nInts, nSegs) {
    const rows = items.map((x) => nearRow(plan, x, nInts, nSegs));
    const head = rows.slice(0, MAX_NEAR).join("");
    const rest = rows.slice(MAX_NEAR);
    return `<ul class="cx-near">${head}</ul>`
      + (rest.length ? `<details class="cx-more-near"><summary>Show ${rest.length} more</summary><ul class="cx-near">${rest.join("")}</ul></details>` : "");
  }

  // returns {summary, body, open} for one plan, or null when the plan says nothing about this area
  function planBlock(plan, c) {
    const year = plan.adopted.slice(0, 4);
    const nInts = data.plans.points.filter((p) => p.plan === plan.id).length;
    const nSegs = data.plans.segments.filter((x) => x.plan === plan.id).length;
    const within = radiusWordsFor(current.miles);
    const bikes = c.onSegments.filter((x) => x.facility);
    const segs = c.onSegments.filter((x) => !x.facility);
    const near = [...c.nearPoints, ...c.nearSegments];
    const here = c.own.length + c.onSegments.length;
    if (plan.unranked && !here && !near.length) return null;

    // the one-line summary shown even when collapsed
    let summary;
    if (c.own.length) summary = plan.unranked ? "Changes recommended at this intersection" : `#${c.own[0].rank} of ${nInts} priority intersections`;
    else if (bikes.length) summary = `${bikeway(bikes[0].facility)} proposed on ${bikes[0].name.split(" from ")[0]}${bikes.length > 1 ? ` and ${bikes.length - 1} more` : ""}`;
    else if (segs.length) summary = plan.unranked ? `Changes recommended on ${segs[0].name.split(/ (from|between) /)[0]}` : `On a priority street: #${segs[0].rank} of ${nSegs}`;
    else if (near.length) {
      const n = near.length, pl = (one, many) => (n === 1 ? one : many);
      summary = plan.id === "bmp" ? `${n} proposed ${pl("bikeway", "bikeways")} within ${within}`
        : plan.unranked ? `Changes recommended at ${n} ${pl("place", "places")} within ${within}`
        : `Not this intersection · ${n} priority ${pl("location", "locations")} within ${within}`;
    }
    else summary = "Not on the plan's lists";

    const parts = [];
    for (const p of c.own) {
      parts.push(plan.unranked
        ? `<p class="cx-plan-lead">The plan recommends changes at this intersection${p.project ? ` (project ${esc(p.project)})` : ""}.</p>`
        : `<p class="cx-plan-lead">This intersection is <strong>#${p.rank} of the ${nInts} intersections</strong> the plan ranks as priorities${p.rank <= 10 ? ", in its top 10" : ""}.</p>`);
      if (p.status) parts.push(`<p>Status: ${esc(p.status.text)}, according to the <a href="${esc(p.status.source)}">city's Transportation Safety page</a> (checked ${C.longDate(p.status.checked)}).</p>`);
      if (p.project_url) parts.push(`<p><a href="${esc(p.project_url)}">The city's project page</a> has the current status.</p>`);
      parts.push(proposalsHtml(plan, p));
    }
    if (bikes.length === 1) {
      const g = bikes[0];
      parts.push(`<p class="cx-plan-lead">The plan proposes <strong>${esc(g.facility.replace(/ \(.*\)$/, ""))}</strong> on ${esc(g.name)}.</p>`
        + `<p class="cx-meta">${esc(g.priority)} priority (project ${esc(g.project)}). Source: <a href="${esc(plan.pdf)}#page=${g.page}">${esc(listLabel(plan))}, page ${g.page}</a>.</p>`);
    } else if (bikes.length) {
      parts.push(`<p class="cx-plan-lead">The plan proposes bikeways on ${bikes.length} stretches through this intersection:</p>`
        + `<ul class="cx-near cx-here">${bikes.map((g) => `<li>${esc(g.name)}<span class="cx-near-meta"><strong>${esc(bikeway(g.facility))}</strong> · ${esc(g.priority)} priority · <a href="${esc(plan.pdf)}#page=${g.page}">source, page ${g.page}</a></span></li>`).join("")}</ul>`);
    }
    for (const g of segs) {
      parts.push(plan.unranked
        ? `<p class="cx-plan-lead">The plan recommends changes on ${esc(g.name)}${g.project ? ` (project ${esc(g.project)})` : ""}.</p>`
        : `<p class="cx-plan-lead">${esc(g.name)} is <strong>#${g.rank} of the ${nSegs} street segments</strong> the plan ranks as priorities.</p>`);
      parts.push(proposalsHtml(plan, g));
    }
    if (near.length) {
      const label = plan.id === "bmp" ? "Proposed bikeways" : plan.unranked ? "Recommended changes" : "Priority locations";
      parts.push(`<h4 class="cx-near-head">${here ? `Also within ${esc(within)}` : `${label} within ${esc(within)}`}</h4>${nearList(plan, near, nInts, nSegs)}`);
    } else if (!here) {
      parts.push(`<p>The plan's ${nInts} priority intersections and ${nSegs} priority street segments don't include this intersection, and none are within ${esc(within)}.</p>`);
    }
    const kinds = new Set([...bikes, ...near].filter((x) => x.facility).map((x) => bikeway(x.facility)));
    for (const k of kinds) if (BIKE_GLOSSARY[k]) parts.push(`<p class="cx-meta">${BIKE_GLOSSARY[k]}</p>`);
    parts.push(`<p class="cx-meta">${esc(plan.method)} From the city's <a href="${esc(plan.url)}">${esc(plan.title)}</a>, adopted ${C.monthYear(plan.adopted)}.</p>`);
    return { summary, label: plan.label || plan.title, year, body: parts.join("") };
  }

  // the plans' changes for this spot, grouped by what they take
  const TAKES = [
    ["quick", "No construction needed", "Changes to signal timing, signs or paint."],
    ["build", "Needs construction", "These need a construction project or new equipment, and money for it, often from grants."],
    ["other", "Studies and enforcement", ""],
  ];
  const FOLD_OVER = 8; // with more items than this, the construction and study lists start folded
  function takesHtml(items) {
    const n = items.quick.length + items.build.length + items.other.length;
    if (!n) return `<p>None of the plans recommend a change at this intersection itself.</p>`;
    const list = (k) => `<ul class="cx-near">${items[k].map((x) => `<li>${esc(x.text)}<span class="cx-near-meta">${esc(C.andList(x.plans))}</span></li>`).join("")}</ul>`;
    const fold = items.quick.length && n > FOLD_OVER;
    return `<div class="cx-takes"><h3>Changes the plans recommend here</h3>`
      + TAKES.filter(([k]) => items[k].length).map(([k, head, note]) => fold && k !== "quick"
        ? `<details class="cx-takes-more"><summary>${head} (${items[k].length})</summary>${note ? `<p class="cx-meta">${note}</p>` : ""}${list(k)}</details>`
        : `<h4>${head}</h4>${note ? `<p class="cx-meta">${note}</p>` : ""}${list(k)}`).join("")
      + `<p class="cx-meta">The plans don't track what has been done since they were adopted, so some of these may already be in place.</p></div>`;
  }

  // "a road safety plan, a bicycle plan, ..." with each linked to the city's page for it
  const PLAN_NOUN = { lrsp: "a road safety plan", bmp: "a bicycle plan", ped: "a pedestrian plan", tod: "a plan for walking to Caltrain stations" };
  function planLinks() {
    const ps = ["lrsp", "bmp", "ped", "tod"].map((id) => data.plans.plans.get(id)).filter(Boolean);
    return C.andList(ps.map((p) => { const [a, ...rest] = PLAN_NOUN[p.id].split(" "); return `${a} <a href="${esc(p.url)}">${esc(rest.join(" "))}</a>`; }));
  }

  function renderPlan(ctx, items) {
    const box = $("#cx-plan");
    if (!ctx) { box.hidden = true; return; }
    const blocks = [...data.plans.plans.values()].map((plan) => planBlock(plan, ctx[plan.id])).filter(Boolean);
    box.innerHTML = `<h2>What the city has planned</h2>
      <p class="cx-plan-intro">The City Council has adopted plans that recommend specific changes at streets and corners across San Mateo: ${planLinks()}. A plan isn't a schedule or a budget, and a change can wait years for money. But a change recommended in an adopted plan is one the city has already put in writing for that place, which is worth pointing to when you ask for it.</p>
      ${takesHtml(items)}
      <h3 class="cx-plans-head">What each plan says</h3>
      <p class="cx-meta">Including places within ${esc(radiusWordsFor(current.miles))}. Tap a plan to see what it says.</p>
      ${blocks.map((b) => `<details class="cx-plan-block">
        <summary><span class="cx-plan-name">${esc(b.label)} <span class="cx-plan-year">${b.year}</span></span>
        <span class="cx-plan-sum">${esc(b.summary)}</span></summary>
        <div class="cx-plan-body">${b.body}</div></details>`).join("")}`;
    box.hidden = false;
  }

  // list: the 10 newest, a "show all" button, and filters by who was hurt
  const FIRST = 10;
  const FILTERS = [
    { key: "all", phrase: "someone was hurt", label: "All", test: () => true },
    { key: "w", phrase: "someone walking was hurt", label: "Walking", test: (c) => c.people.some((p) => p[0] === "w") },
    { key: "b", phrase: "someone on a bike was hurt", label: "On a bike", test: (c) => c.people.some((p) => p[0] === "b") },
    { key: "s", phrase: "someone on a scooter was hurt", label: "On a scooter", test: (c) => c.people.some((p) => p[0] === "s") },
    { key: "v", phrase: "someone in a vehicle was hurt", label: "In a vehicle", test: (c) => c.people.some((p) => p[0] === "v") },
    { key: "bad", phrase: "someone was seriously hurt or killed", label: "Seriously hurt or killed", test: (c) => c.people.some((p) => p[1] !== "o") },
  ];
  let filter = "all", showAll = false;

  function crashRow(c, i) {
    const mode = c.killed ? "killed" : C.MODES[c.mode].key;
    const dot = c.killed ? `<span class="cx-key cx-key-killed" aria-hidden="true"></span>`
      : c.mode === "v" ? `<span class="cx-key cx-key-ring" aria-hidden="true"></span>`
      : `<span class="cx-key" style="background:var(--${mode})" aria-hidden="true"></span>`;
    const who = cap(c.killed ? C.deathLine(c.people) : C.describePeople(c.people));
    const where = c.killed ? "" : `${esc(c.place || "Location from police report")}${c.approx ? " (approximate)" : ""}`;
    const head = `<span class="cx-date">${C.longDate(c.date)}</span>`
      + `<span class="cx-where">${where}</span><span class="cx-who">${dot}${esc(who)}</span>`;
    if (c.killed) return `<li class="cx-death" id="cx-c-${i}"><div class="cx-row">${head}</div></li>`;
    return `<li id="cx-c-${i}"><details><summary class="cx-row">${head}</summary>${detailsHtml(c)}</details></li>`;
  }

  function renderList(near) {
    const chips = FILTERS.map((f) => ({ ...f, n: near.filter(f.test).length })).filter((f) => f.key === "all" || f.n > 0);
    if (!chips.some((f) => f.key === filter)) filter = "all";
    $("#cx-filters").innerHTML = near.length > FIRST || filter !== "all"
      ? chips.map((f) => `<button type="button" class="cx-chip" data-f="${f.key}" aria-pressed="${f.key === filter}">${esc(f.label)} <span>${f.n}</span></button>`).join("")
      : "";
    const test = FILTERS.find((f) => f.key === filter).test;
    const rows = near.map((c, i) => [c, i]).filter(([c]) => test(c));
    const visible = showAll ? rows : rows.slice(0, FIRST);
    $("#cx-list").innerHTML = visible.map(([c, i]) => crashRow(c, i)).join("");
    $("#cx-list-count").textContent = !near.length ? "No crashes in which someone was hurt."
      : `${rows.length} ${rows.length === 1 ? "crash" : "crashes"} in which ${FILTERS.find((f) => f.key === filter).phrase}, newest first.`;
    const more = $("#cx-more");
    more.hidden = rows.length <= visible.length;
    more.textContent = `Show all ${rows.length}`;
  }
  $("#cx-more").addEventListener("click", () => { showAll = true; renderList(current.near); });
  $("#cx-filters").addEventListener("click", (e) => {
    const b = e.target.closest(".cx-chip");
    if (!b) return;
    filter = b.dataset.f;
    showAll = false;
    renderList(current.near);
  });
  // "Full details" in a map popup opens that crash in the list, clearing any filter
  $("#cx-map").addEventListener("click", (e) => {
    const b = e.target.closest(".cx-goto");
    if (!b) return;
    const i = +b.dataset.i;
    if (!$(`#cx-c-${i}`)) { filter = "all"; showAll = true; renderList(current.near); }
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
    box.innerHTML = `<h3>Email your council member</h3>`
      + `<p>${esc(int.label)} is in City Council District ${int.district}, represented by ${esc(m.title)} ${esc(m.name)}. The email starts with this page's numbers and a question; add a sentence of your own.</p>`
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
