// Default-settings headline and context for intersections, using the same
// core.js the page runs. Usage: node prerender.mjs <data dir> [id ...]
// Prints JSON {id: {label, district, headline, context, n, walk, bike, scooter, vehicle, killed}}.
import fs from "node:fs";
import path from "node:path";
import * as C from "./static/core.js";

const [dir, ...ids] = process.argv.slice(2);
const data = C.prepare(
  JSON.parse(fs.readFileSync(path.join(dir, "crashes.json"))),
  JSON.parse(fs.readFileSync(path.join(dir, "intersections.json"))),
);
const s = C.readSettings("", data.meta);
const dist = C.distribution(data, s.miles, s.y0, s.y1);
const out = {};
for (const i of ids.length ? ids.map((id) => data.byId.get(id)) : data.ints) {
  if (!i) continue;
  const t = C.tally(C.nearby(data, i.px, i.py, s.miles, s.y0, s.y1));
  out[i.id] = {
    label: i.label, district: i.district, lon: i.lon, lat: i.lat,
    headline: C.headline(i.label, t, s, data.meta.years[1]),
    context: C.context(t.n, dist, s),
    n: t.n, walk: t.w, bike: t.b, scooter: t.s, vehicle: t.v, killed: t.killed,
    years: C.yearsPhrase(s.y0, s.y1, data.meta.years[1]),
  };
}
out._meta = { dataThrough: C.dataThrough(data.meta), median: C.median(dist), ...data.meta };
process.stdout.write(JSON.stringify(out));
