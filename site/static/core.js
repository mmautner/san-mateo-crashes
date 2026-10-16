// Counting and wording. No DOM: used by the page and, under Node, by the build
// to pre-render each intersection page at the default settings.

export const RADII = [
  { miles: 0.125, words: "an eighth of a mile", short: "⅛ mile" },
  { miles: 0.25, words: "a quarter mile", short: "¼ mile" },
  { miles: 0.5, words: "half a mile", short: "½ mile" },
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
  return { meta: crashData.meta, crashes, ints, grid, byId: new Map(ints.map((i) => [i.id, i])) };
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
  const where = `within ${radiusWords(s.miles)} of ${label}`;
  if (t.n === 0) return `${when}, police reported no one hurt in crashes ${where}.`;
  const parts = MODE_ORDER.filter((m) => t[m] > 0).map((m) => n(t[m], MODES[m].one, MODES[m].many));
  const people = t.n === 1 ? "1 person was hurt in a crash" : `${t.n} people were hurt in crashes`;
  let text = `${when}, at least ${people} ${where}: ${parts.join(", ")}.`;
  if (t.killed > 0) {
    text += t.n === 1 ? " They were killed." : ` ${t.killed} of them ${t.killed === 1 ? "was" : "were"} killed.`;
  }
  return text;
}

export function context(count, sorted, s) {
  const below = sorted.filter((c) => c < count).length / sorted.length;
  if (below >= 0.5) {
    const pct = Math.min(99, Math.floor(below * 100));
    return `That's more than ${pct}% of San Mateo intersections over the same years.`;
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
  return `Police reports through ${monthYear(meta.data_through)}`;
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
