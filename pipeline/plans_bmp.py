"""Extract the 2020 Bicycle Master Plan's project list into site/plans/bmp.json.

    python pipeline/plans_bmp.py      # then: python pipeline/plans.py

Source: City of San Mateo, 2020 Bicycle Master Plan (adopted April 6, 2020),
Appendix E "Project List and Cost Estimates" (appendices PDF, pages 109-116).
The table's cells wrap and merge, so it is read word by word: columns come from
each page's header words, and a row starts a new segment only when both of its
limit columns have text (otherwise it continues the row above). Rerunning on the
same PDF gives the same output.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
CACHE = HERE / "cache" / "plans"
PDF_URL = "https://www.cityofsanmateo.org/DocumentCenter/View/80922"
PAGES = range(109, 117)  # 1-based pages of Appendix E in the appendices PDF
OUT = HERE.parent / "site" / "plans" / "bmp.json"

PRIORITY = ["High", "Medium-High", "Medium-Low", "Low"]
FACILITY = {  # plan's term -> plain words
    "bike lane": "a bike lane",
    "buffered bike lane": "a bike lane with a painted buffer",
    "separated bl": "a bike lane separated from traffic",
    "separated bike lane": "a bike lane separated from traffic",
    "bike blvd": "a bike boulevard (a calmer street with signs and markings for bikes)",
    "bike route": "a signed bike route",
    "shared-use path": "a walking and biking path",
    "shared use path": "a walking and biking path",
    "class iii": "a signed bike route",
    "buffered bl": "a bike lane with a painted buffer",
}
# How the plan writes some names, and what to look for on the map instead
ALIASES = {"Av": "Ave", "Bl": "Blvd", "Pk": "Pkwy", "Ci": "Cir", "Wy": "Way"}
NOT_A_STREET = re.compile(r"city limit|bay trail|us-101|sr-92|i-280|caltrain|path$|trail$|creek|park$|^$", re.I)


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    pdf = CACHE / "bmp_appendices.pdf"
    if not pdf.exists():
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "san-mateo-crashes pipeline"})
        pdf.write_bytes(urllib.request.urlopen(req).read())
    return pdf


SUFFIX = {"Av", "Ave", "St", "Dr", "Rd", "Bl", "Blvd", "Wy", "Way", "Ci", "Cir", "Pk", "Pkwy", "Ln", "Ct", "Pl"}
# Single cells the table layout scrambles beyond the general rules: (street, from, to) as printed -> as meant
FIXES = {("Alameda de las Pulgas Rd", "Crystal Springs", "26th Av"): ("Alameda de las Pulgas", "Crystal Springs Rd", "26th Av")}


def street(s):
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split(" ")
    # a name ends at its first street suffix; anything after is a stray note from another column
    for i, w in enumerate(words[:-1]):
        if w in SUFFIX and not s.startswith(("Alameda de las Pulgas",)):
            s = " ".join(words[: i + 1])
            break
    words = s.split(" ")
    if words and words[-1] in ALIASES:
        words[-1] = ALIASES[words[-1]]
    return " ".join(words)


# Table furniture that bleeds into the last row of a page
JUNK = re.compile(r"\$|Northern/|Southern/|Western Limit|Eastern Limit|Proposed|Facility$|Prioritization|Score|"
                  r"Implementation|^Number$|Cost Estimate|Rapid|^Network$|^Partial:|bike lanes\)|Total Cost|^\(level")
WRAP = re.compile(r"^(Av|Ave|Bl|Blvd|St|Dr|Rd|Wy|Ci|Pk|Path|Network|\((East|West|North|South)\)|las Pulgas|de las Pulgas)$")


def split_lines(cell):
    """A cell may stack several segments, one per line; rejoin words that wrapped."""
    out = []
    for line in (cell or "").split("\n"):
        line = line.strip()
        if not line or JUNK.search(line):
            continue
        if out and WRAP.match(line):
            out[-1] += " " + line
        else:
            out.append(line)
    return out


def fit(lines, n):
    """Merge wrapped fragments until a column has n lines: the shortest line joins the one above."""
    lines = list(lines)
    while len(lines) > n and len(lines) > 1:
        i = min(range(1, len(lines)), key=lambda k: (len(lines[k]), k))
        lines[i - 1] += " " + lines.pop(i)
    return lines


def segments_from(pdf):
    segments, priority, project = [], None, None
    for page_no in PAGES:
        for table in pdf.pages[page_no - 1].extract_tables():
            for row in table:
                vals = [c for c in row if c and c.strip()]
                if not vals:
                    continue
                flat = " ".join(v.replace("\n", " ") for v in vals)
                m = re.match(r"(High|Medium-High|Medium-Low|Low) Priority Projects", flat)
                if m:
                    priority = m.group(1)
                    continue
                if flat.startswith("Project") or "Western Limit" in flat or priority is None:
                    continue
                if re.fullmatch(r"\d+", vals[0].strip()):
                    project = int(vals[0])
                    vals = vals[1:]
                if len(vals) >= 4:
                    cols = [split_lines(v) for v in vals[:4]]
                    n = len(cols[3])  # the facility column rarely wraps
                    cols = [fit(c, n) for c in cols]
                    if any(len(c) != n for c in cols):
                        sys.exit(f"page {page_no}, project {project}: can't align {cols}")
                    for street, a, b, fac in zip(*cols):
                        segments.append({"project": project, "priority": priority, "street": street,
                                         "from": a, "to": b, "facility_raw": fac, "page": page_no})
                elif segments:
                    # a lone wrapped fragment ("Av", "(East)", "Path") belongs to the row above
                    for v in vals:
                        for frag in split_lines(v):
                            if len(frag.split()) > 3 or re.search(r"\d", frag):
                                continue  # not a wrapped word; stray table text
                            key = "facility_raw" if frag == "Path" else "street"
                            segments[-1][key] += " " + frag
    return segments


def main():
    with pdfplumber.open(fetch()) as pdf:
        segments = segments_from(pdf)

    out, unplaced, unknown = [], [], set()
    for s in segments:
        fac = re.sub(r"\s+", " ", s["facility_raw"]).strip()
        plain = FACILITY.get(fac.lower())
        if plain is None:
            unknown.add(fac)
            plain = fac
        raw = (re.sub(r"\s+", " ", s["street"]).strip(), re.sub(r"\s+", " ", s["from"]).strip(), re.sub(r"\s+", " ", s["to"]).strip())
        st, fr, to = FIXES.get(raw, raw)
        name_street = street(re.sub(r"\((East|West|North|South)\)", "", st))
        a, b = street(re.sub(r"\((East|West|North|South)\)", "", fr)), street(re.sub(r"\((East|West|North|South)\)", "", to))
        entry = {"project": s["project"], "priority": s["priority"], "facility": plain,
                 "name": f"{name_street} from {a} to {b}", "street": name_street, "from": a, "to": b, "page": s["page"]}
        if NOT_A_STREET.search(name_street) or NOT_A_STREET.search(a) or NOT_A_STREET.search(b):
            # an end at the city limit, a freeway or a trail: keep it, matched by street name only later
            entry["open_end"] = True
        out.append(entry)

    plan = {
        "_readme": "Generated by pipeline/plans_bmp.py from Appendix E of the 2020 Bicycle Master Plan. "
                   "Do not edit by hand; change ALIASES or FACILITY in the script and rerun.",
        "id": "bmp",
        "title": "Bicycle Master Plan",
        "short": "the city's 2020 bicycle plan",
        "adopted": "2020-04-06",
        "url": "https://www.cityofsanmateo.org/3944/Bicycle-Master-Plan-2020",
        "pdf": PDF_URL,
        "method": "The bicycle plan scored each proposed bikeway on safety, comfort, equity and expected use "
                  "(including where bike crashes had happened) and grouped them from High to Low priority. "
                  "Some may have been built since 2020.",
        "unranked": True,
        "intersections": [],
        "segments": out,
    }
    OUT.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
    by = {p: sum(1 for s in out if s["priority"] == p) for p in PRIORITY}
    print(f"{len(segments)} segments in {len({s['project'] for s in out})} projects {by}", file=sys.stderr)
    if unknown:
        print(f"  facility terms with no plain wording: {sorted(unknown)}", file=sys.stderr)


if __name__ == "__main__":
    main()
