// Counting and wording. No DOM: used by the page and, under Node, by the build
// to pre-render each intersection page at the default settings.

// walk: at about 3 miles an hour
export const RADII = [
  { miles: 0.125, words: "an eighth of a mile", short: "⅛ mile", walk: "a 2- to 3-minute walk", menu: "2–3 min walk" },
  { miles: 0.25, words: "a quarter mile", short: "¼ mile", walk: "about a 5-minute walk", menu: "5 min walk" },
  { miles: 0.5, words: "half a mile", short: "½ mile", walk: "about a 10-minute walk", menu: "10 min walk" },
];
export const DEFAULT_RADIUS = 0.25;
const M_PER_MILE = 1609.344;

export const MODES = {
  w: { key: "walk", one: "walking", many: "walking", noun: "person walking" },
  b: { key: "bike", one: "on a bike", many: "on bikes", noun: "person on a bike" },
  s: { key: "scooter", one: "on a scooter", many: "on scooters", noun: "person on a scooter" },
  v: { key: "vehicle", one: "in a vehicle", many: "in vehicles", noun: "person in a vehicle" },
};
export const MODE_ORDER = ["w", "b", "s", "v"]; // most to least exposed
export const SEVERITY = { k: "killed", s: "seriously injured", o: "injured" };

const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

// Equirectangular projection to meters; accurate to well under 1% over a city.
const LAT0 = 37.56;
const KX = 111320 * Math.cos((LAT0 * Math.PI) / 180);
const KY = 110574;
export const toXY = (lon, lat) => [lon * KX, lat * KY];

export function prepare(crashData, intersections) {
  const T = crashData.text;
  const crashes = crashData.crashes.map(([x, y, date, place, how, people, d]) => {
    const lon = x / 1e5, lat = y / 1e5;
    const [px, py] = toXY(lon, lat);
    const codes = people.match(/../g);
    return {
      lon, lat, px, py, date, year: +date.slice(0, 4),
      place: place >= 0 ? crashData.places[place] : null,
      approx: how === 1, people: codes,
      killed: codes.some((c) => c[1] === "k"),
      mode: MODE_ORDER.find((m) => codes.some((c) => c[0] === m)),
      details: d ? { hour: d[0] < 0 ? null : d[0], light: T.light[d[1]], type: T.type[d[2]], cause: T.cause[d[3]],
        who: T.who[d[4]], ped: T.ped[d[5]], hitrun: d[6] === 1 } : null,
    };
  });
  const ints = intersections.map(([id, label, x, y, district]) => {
    const lon = x / 1e5, lat = y / 1e5;
    const [px, py] = toXY(lon, lat);
    return { id, label, lon, lat, px, py, district };
  });
  // 400 m grid for neighbor lookups
  const grid = new Map();
  for (const c of crashes) {
    const k = `${Math.floor(c.px / 400)},${Math.floor(c.py / 400)}`;
    if (!grid.has(k)) grid.set(k, []);
    grid.get(k).push(c);
  }
  // reported crashes where no one was hurt: position and year only
  const noInjury = new Map();
  for (const [x, y, yy] of crashData.no_injury || []) {
    const [px, py] = toXY(x / 1e5, y / 1e5);
    const k = `${Math.floor(px / 400)},${Math.floor(py / 400)}`;
    if (!noInjury.has(k)) noInjury.set(k, []);
    noInjury.get(k).push([px, py, 2000 + yy]);
  }
  return { meta: crashData.meta, crashes, ints, grid, noInjury, byId: new Map(ints.map((i) => [i.id, i])) };
}

export function nearby(data, px, py, miles, y0, y1) {
  const r = miles * M_PER_MILE, r2 = r * r, n = Math.ceil(r / 400);
  const gx = Math.floor(px / 400), gy = Math.floor(py / 400);
  const out = [];
  for (let i = -n; i <= n; i++) for (let j = -n; j <= n; j++) {
    for (const c of data.grid.get(`${gx + i},${gy + j}`) || []) {
      if (c.year < y0 || c.year > y1) continue;
      const dx = c.px - px, dy = c.py - py;
      if (dx * dx + dy * dy <= r2) out.push(c);
    }
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : -1));
}

export function tally(crashes) {
  const t = { n: 0, killed: 0, serious: 0, w: 0, b: 0, s: 0, v: 0 };
  for (const c of crashes) for (const p of c.people) {
    t.n++; t[p[0]]++;
    if (p[1] === "k") t.killed++;
    if (p[1] === "s") t.serious++;
  }
  return t;
}

// People hurt near every intersection, sorted ascending: the comparison set.
export function distribution(data, miles, y0, y1) {
  return data.ints.map((i) => tally(nearby(data, i.px, i.py, miles, y0, y1)).n).sort((a, b) => a - b);
}

export function median(sorted) {
  const m = sorted.length >> 1;
  return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
}

const radiusWords = (miles) => (RADII.find((r) => r.miles === miles) || { words: `${miles} mile` }).words;

export function yearsPhrase(y0, y1, lastYear) {
  if (y0 === y1) return `In ${y0}`;
  if (y1 === lastYear) return `Since ${y0}`;
  return `From ${y0} through ${y1}`;
}

const n = (k, one, many) => `${k} ${k === 1 ? one : many}`;

export function headline(label, t, s, lastYear) {
  const when = yearsPhrase(s.y0, s.y1, lastYear);
  const r = RADII.find((x) => x.miles === s.miles);
  const where = `within ${radiusWords(s.miles)}${r ? ` (${r.walk})` : ""} of ${label}`;
  if (t.n === 0) return `${when}, police reported no one hurt in crashes ${where}.`;
  const parts = MODE_ORDER.filter((m) => t[m] > 0).map((m) => n(t[m], MODES[m].one, MODES[m].many));
  const people = t.n === 1 ? "1 person was hurt in a crash" : `${t.n} people were hurt in crashes`;
  let text = `${when}, at least ${people} ${where}: ${parts.join(", ")}.`;
  // say plainly how many were badly hurt, so minor injuries aren't mistaken for the whole count
  if (t.n === 1) {
    if (t.killed) text += " They were killed.";
    else if (t.serious) text += " They were seriously injured.";
  } else {
    const was = (k) => (k === 1 ? "was" : "were");
    const bad = [];
    if (t.serious) bad.push(`${t.serious} ${was(t.serious)} seriously injured`);
    if (t.killed) bad.push(`${t.killed} ${was(t.killed)} killed`);
    if (bad.length) text += ` ${bad[0].replace(/^(\d+)/, "$1 of them")}${bad[1] ? ` and ${bad[1]}` : ""}.`;
  }
  return text;
}

// "At the intersection": within this distance of where the streets meet
export const AT_INTERSECTION_M = 40;

export function atIntersection(data, int, s) {
  return tally(nearby(data, int.px, int.py, AT_INTERSECTION_M / M_PER_MILE, s.y0, s.y1)).n;
}

export function atIntersectionSentence(k, total) {
  if (!total) return "";
  if (!k) return "None of them were hurt at the intersection itself; those crashes were on nearby streets.";
  if (k === total) return total === 1 ? "That crash was at the intersection itself." : "All of them were hurt at the intersection itself.";
  return `${k} of them ${k === 1 ? "was" : "were"} hurt at the intersection itself.`;
}

export function context(count, sorted, s) {
  const below = sorted.filter((c) => c < count).length / sorted.length;
  if (below >= 0.5) {
    const pct = Math.min(99, Math.floor(below * 100));
    return `More people were hurt near here than near ${pct}% of San Mateo intersections over the same years.`;
  }
  const med = Math.round(median(sorted));
  return `For comparison, the typical San Mateo intersection had ${med} ${med === 1 ? "person" : "people"} hurt within ${radiusWords(s.miles)} over the same years.`;
}

export function monthYear(date) {
  return `${MONTHS[+date.slice(5, 7) - 1]} ${date.slice(0, 4)}`;
}

export function longDate(date) {
  if (date.length === 7) return monthYear(date);
  return `${MONTHS[+date.slice(5, 7) - 1].slice(0, 3)} ${+date.slice(8, 10)}, ${date.slice(0, 4)}`;
}

// "1 walking, seriously injured; 2 in vehicles, injured"
export function describePeople(codes) {
  const groups = new Map();
  for (const c of codes) groups.set(c, (groups.get(c) || 0) + 1);
  return [...groups].map(([c, k]) => {
    const m = MODES[c[0]];
    const who = k === 1 ? m.noun : `${k} people ${m.many}`;
    return `${who}, ${SEVERITY[c[1]]}`;
  }).join("; ");
}

export function dataThrough(meta) {
  const y = +meta.data_through.slice(0, 4);
  return `Police reports through ${monthYear(meta.data_through)}. ${y + 1} will be added once its reports are in, in spring ${y + 2}`;
}

export function gapNote(meta, y0, y1) {
  const g = meta.gaps.filter((g) => +g.from.slice(0, 4) <= y1 && +g.to.slice(0, 4) >= y0);
  return g.map((g) => `${g.agency} reports from ${monthYear(g.from)} through ${monthYear(g.to)} are missing from the state's data, so these years count too few.`).join(" ");
}

// Settings <-> URL query. Defaults are left out of the URL.
export function readSettings(search, meta) {
  const q = new URLSearchParams(search);
  const [first, last] = meta.years, [d0, d1] = meta.default_years;
  const clamp = (v, d) => (Number.isInteger(v) && v >= first && v <= last ? v : d);
  let y0 = clamp(parseInt(q.get("from"), 10), d0), y1 = clamp(parseInt(q.get("to"), 10), d1);
  if (y0 > y1) [y0, y1] = [y1, y0];
  const r = parseFloat(q.get("r"));
  return { miles: RADII.some((x) => x.miles === r) ? r : DEFAULT_RADIUS, y0, y1 };
}

export function writeSettings(s, meta) {
  const q = new URLSearchParams();
  if (s.miles !== DEFAULT_RADIUS) q.set("r", s.miles);
  if (s.y0 !== meta.default_years[0]) q.set("from", s.y0);
  if (s.y1 !== meta.default_years[1]) q.set("to", s.y1);
  const str = q.toString();
  return str ? `?${str}` : "";
}

// Search: "3rd & b", "aragon blvd", "123 monte diablo ave"
const ALIASES = { avenue: "ave", av: "ave", street: "st", boulevard: "blvd", bl: "blvd", drive: "dr",
  road: "rd", lane: "ln", court: "ct", place: "pl", parkway: "pkwy", north: "n", south: "s", east: "e",
  west: "w", saint: "st", first: "1st", second: "2nd", third: "3rd", fourth: "4th", fifth: "5th" };
const words = (s) => s.toLowerCase().replace(/[^a-z0-9& ]+/g, " ").split(/\s+/).filter(Boolean)
  .map((w) => ALIASES[w] || w);

export function search(data, query, limit = 8) {
  let q = query.toLowerCase().replace(/\s+(and|at|@|\/)\s+/g, " & ").replace(/^\s*\d+[a-z]?\s+(?=\D)/, "");
  const sides = q.split("&").map(words).filter((s) => s.length);
  if (!sides.length) return [];
  const matchSide = (side, street) => {
    const ws = words(street);
    return side.every((t) => ws.some((w) => w.startsWith(t)));
  };
  const hits = [];
  for (const i of data.ints) {
    const [a, b] = i.label.split(" & ");
    let ok;
    if (sides.length === 1) ok = matchSide(sides[0], a) || matchSide(sides[0], b);
    else ok = (matchSide(sides[0], a) && matchSide(sides[1], b)) || (matchSide(sides[0], b) && matchSide(sides[1], a));
    if (ok) hits.push(i);
    if (hits.length > 400) break;
  }
  return hits.sort((x, y) => x.label.localeCompare(y.label, "en", { numeric: true })).slice(0, limit);
}

export function nearestIntersection(data, lon, lat) {
  const [px, py] = toXY(lon, lat);
  let best = null, bd = Infinity;
  for (const i of data.ints) {
    const d = (i.px - px) ** 2 + (i.py - py) ** 2;
    if (d < bd) { bd = d; best = i; }
  }
  return { int: best, meters: Math.sqrt(bd) };
}

// Deaths: month, year and mode only. Others hurt in the same crash are a count.
export function deathLine(codes) {
  const killed = codes.filter((c) => c[1] === "k");
  const modes = [...new Set(killed.map((c) => c[0]))].map((m) => MODES[m]);
  const who = killed.length === 1 ? `A ${modes[0].noun} was killed` : `${killed.length} people (${modes.map((m) => m.many).join(", ")}) were killed`;
  const others = codes.length - killed.length;
  return others ? `${who}. ${others} other ${others === 1 ? "person was" : "people were"} hurt.` : `${who}.`;
}

// ------------------------------------------------------------------ crash details

const clock = (h) => `${h % 12 || 12} ${h < 12 ? "am" : "pm"}`;
export function hourText(h) {
  if (h == null) return "";
  return `Between ${clock(h).replace(/ (am|pm)$/, (h < 12) === (h + 1 < 12 || h + 1 === 24) ? "" : " $1")} and ${clock((h + 1) % 24)}`;
}

// [label, value] rows for one crash's card. Crashes where someone died have none.
export function detailRows(c) {
  const d = c.details;
  if (!d) return [];
  const rows = [
    ["Time", hourText(d.hour)],
    ["Light", d.light],
    ["Type of crash", d.type],
    ["Most at fault, per the officer", d.who],
    ["Cause the officer recorded", d.cause],
  ];
  if (c.people.some((p) => p[0] === "w")) rows.push(["The person walking was", d.ped]);
  if (d.hitrun) rows.push(["Hit and run", "Yes, a driver left the scene"]);
  return rows.filter(([, v]) => v);
}

const top = (counts, k) => [...counts].filter(([v]) => v).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, k);
const tallyBy = (xs, f) => { const m = new Map(); for (const x of xs) { const v = f(x); m.set(v, (m.get(v) || 0) + 1); } return m; };

// What the reports say across the crashes in range (crashes with a death are left out).
export function patterns(near) {
  const cs = near.filter((c) => c.details);
  const walking = cs.filter((c) => c.people.some((p) => p[0] === "w"));
  return {
    n: cs.length,
    causes: top(tallyBy(cs, (c) => c.details.cause), 3),
    types: top(tallyBy(cs, (c) => c.details.type), 3),
    who: top(tallyBy(cs, (c) => c.details.who), 3),
    dark: cs.filter((c) => /^Dark/.test(c.details.light)).length,
    walking: walking.length,
    crosswalk: walking.filter((c) => /^Crossing in (the|a mid-block) crosswalk/.test(c.details.ped)).length,
    hitrun: cs.filter((c) => c.details.hitrun).length,
  };
}

export const MIN_PATTERN_CRASHES = 5;
const lower = (s) => s.charAt(0).toLowerCase() + s.slice(1);

// One sentence for the top of the page and the council email, only when a pattern is real.
export function patternSentence(p) {
  if (p.n < MIN_PATTERN_CRASHES || !p.causes.length || p.causes[0][1] < 3) return "";
  const k = p.causes[0][1];
  const tied = p.causes.filter(([, n]) => n === k).map(([c]) => lower(c));
  if (tied.length === 1) return `The cause police recorded most often here: ${tied[0]} (${k} of ${p.n} crashes).`;
  const list = tied.length === 2 ? tied.join(" and ") : `${tied.slice(0, -1).join(", ")}, and ${tied.at(-1)}`;
  return `The causes police recorded most often here: ${list} (${k} crashes each, of ${p.n}).`;
}

// ------------------------------------------------------------------ crashes where no one was hurt

export function noInjuryCount(data, px, py, miles, y0, y1) {
  const r = miles * M_PER_MILE, r2 = r * r, n = Math.ceil(r / 400);
  const gx = Math.floor(px / 400), gy = Math.floor(py / 400);
  let count = 0;
  for (let i = -n; i <= n; i++) for (let j = -n; j <= n; j++) {
    for (const [x, y, yr] of data.noInjury.get(`${gx + i},${gy + j}`) || []) {
      if (yr >= y0 && yr <= y1 && (x - px) ** 2 + (y - py) ** 2 <= r2) count++;
    }
  }
  return count;
}

export function noInjurySentence(k, s) {
  if (!k) return "";
  return `Police also took reports on ${k} ${k === 1 ? "crash" : "crashes"} within ${radiusWords(s.miles)} where no one was hurt. Nationally, about 60% of crashes like these are never reported to police.`;
}

// ------------------------------------------------------------------ city plans

function distToLine(px, py, line) {
  let best = Infinity;
  for (let k = 0; k < line.length - 1; k++) {
    const [ax, ay] = line[k], [bx, by] = line[k + 1];
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
    const t = L2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L2)) : 0;
    best = Math.min(best, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
  }
  return best;
}

export function preparePlans(plans) {
  if (!plans) return null;
  return {
    plans: new Map(plans.plans.map((p) => [p.id, p])),
    projects: plans.projects,
    kinds: plans.kinds || {},
    points: plans.intersections.map((p) => { const [px, py] = toXY(p.lon, p.lat); return { ...p, px, py }; }),
    segments: plans.segments.map((s) => ({ ...s, xy: s.line.map(([lon, lat]) => toXY(lon, lat)) })),
  };
}

const ON_SEGMENT_M = 40;

// What each city plan says about this intersection and its surroundings, keyed by plan id.
export function planContext(plans, int, miles) {
  if (!plans) return null;
  const r = miles * M_PER_MILE;
  const byRank = (a, b) => (a.rank ?? 0) - (b.rank ?? 0) || Math.hypot(a.px - int.px, a.py - int.py) - Math.hypot(b.px - int.px, b.py - int.py);
  const out = {};
  for (const id of plans.plans.keys()) {
    const pts = plans.points.filter((p) => p.plan === id), segs = plans.segments.filter((s) => s.plan === id);
    const own = pts.filter((p) => p.id === int.id);
    const onSegments = segs.filter((s) => distToLine(int.px, int.py, s.xy) <= ON_SEGMENT_M);
    out[id] = {
      own, onSegments,
      nearPoints: pts.filter((p) => p.id !== int.id && Math.hypot(p.px - int.px, p.py - int.py) <= r).sort(byRank),
      nearSegments: segs.filter((s) => !onSegments.includes(s) && distToLine(int.px, int.py, s.xy) <= r).sort(byRank),
    };
  }
  return out;
}

// Factual sentences for the council email: the ranked safety plan always, other plans when they name this spot.
export function planSentence(plans, ctx, s) {
  if (!ctx) return "";
  const out = [];
  for (const plan of plans.plans.values()) {
    const c = ctx[plan.id], year = plan.adopted.slice(0, 4);
    const nInts = plans.points.filter((p) => p.plan === plan.id).length;
    if (plan.unranked) {
      const bike = c.onSegments.find((x) => x.facility);
      if (bike) out.push(`The city's ${year} ${plan.title} proposes ${bike.facility.replace(/ \(.*\)$/, "")} on ${bike.name} (${bike.priority} priority).`);
      else if (c.own.length) out.push(`The city's ${year} ${plan.title} recommends changes at this intersection.`);
      else if (c.onSegments.length) out.push(`The city's ${year} ${plan.title} recommends changes on ${c.onSegments[0].name}.`);
      continue;
    }
    const own = c.own[0], seg = c.onSegments[0];
    const near = c.nearPoints.length + c.nearSegments.length;
    if (own) out.push(`The city's ${year} ${plan.title} lists this intersection as #${own.rank} of ${nInts} priority intersections.`);
    else if (seg) out.push(`The city's ${year} ${plan.title} lists ${seg.name} as a priority street segment.`);
    else if (near) out.push(`The city's ${year} ${plan.title} lists ${near} priority ${near === 1 ? "location" : "locations"} within ${radiusWords(s.miles)} of this intersection, but not this intersection itself.`);
    else out.push(`This intersection is not among the ${nInts} priority intersections in the city's ${year} ${plan.title}.`);
  }
  return out.join(" ");
}

// The changes the plans recommend at this intersection (or on a plan's street segment through it),
// sorted by what they take: quick (signal timing, signs or paint), build, or other (studies, enforcement).
// Each: {text, kind, plans: [plan labels]}. A bikeway reads "A bike lane on 3rd Ave from ...".
export function planItems(plans, ctx) {
  const out = { quick: [], build: [], other: [] }, seen = new Map();
  if (!ctx) return out;
  const add = (text, key, plan) => {
    const kind = plans.kinds?.[key];
    if (!kind) return;
    const who = `${plan.label}, ${plan.adopted.slice(0, 4)}`;
    if (seen.has(text)) { const it = seen.get(text); if (!it.plans.includes(who)) it.plans.push(who); return; }
    const it = { text, kind, plans: [who] };
    seen.set(text, it);
    out[kind].push(it);
  };
  for (const plan of plans.plans.values()) {
    const c = ctx[plan.id];
    for (const e of [...c.own, ...c.onSegments]) {
      if (e.facility) {
        const f = e.facility.replace(/ \(.*\)$/, "");
        add(`${f.charAt(0).toUpperCase()}${f.slice(1)} on ${e.name}`, e.facility, plan);
        continue;
      }
      const src = e.sooner || e.other ? e : plans.projects[plan.id]?.[String(e.project)];
      for (const t of [...(src?.sooner || []), ...(src?.later || []), ...(src?.other || [])]) add(t, t, plan);
    }
  }
  return out;
}

// "a, b and c"
export function andList(xs) {
  return xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

const lowerWord = (t) => (/^(A |[A-Z][a-z])/.test(t) ? lower(t) : t); // "B St ..." stays

// Email sentence: the changes the plans recommend here that don't need construction.
export function actionSentences(items) {
  if (!items.quick.length) return "";
  const xs = items.quick.map((x) => lowerWord(x.text));
  const shown = xs.length > 4 ? [...xs.slice(0, 3), `${xs.length - 3} more`] : xs;
  return `The city's plans recommend changes here that don't need construction: ${andList(shown)}.`;
}

// People hurt near a point in each year, for the by-year chart.
export function byYear(data, px, py, miles) {
  const [y0, y1] = data.meta.years;
  const out = [];
  for (let y = y0; y <= y1; y++) out.push({ year: y, n: tally(nearby(data, px, py, miles, y, y)).n });
  return out;
}

export function gapYears(meta) {
  const ys = new Set();
  for (const g of meta.gaps) for (let y = +g.from.slice(0, 4); y <= +g.to.slice(0, 4); y++) ys.add(y);
  return ys;
}
