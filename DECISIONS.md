# Decisions

Why the site is the way it is, newest first: what was considered, what was chosen, and why.
The aim throughout is that every number and claim can be defended to a skeptic: conservative,
sourced, and in plain language.

## 2026-10-16 — No repaving schedule; plans explained before they're listed

**Considered:** the city's "Proposed Road Segments for Resurfacing (2025–2029)" table (January
2025) was extracted and matched to corners (343 of 435 segments placed). Pages and the council
email said when a corner's streets were due for repaving, since repaving covers a street's
markings and is the cheapest time to change them.

**Chosen:** removed before release. The city marks the list "for coordination purposes only."
It was already out of date in places, and repaving itself is thinly funded. A static page citing
a proposed schedule would drift out of date and could set expectations neither the site nor the city can
meet.

**Also:** the plans section now opens by saying what an adopted plan is and isn't (not a schedule
or a budget, but the city's own written recommendation for a place). It links each plan, and it
sorts each corner's recommended changes by what they take (`site/plans/kinds.json`). "No
construction needed" is limited to signal timing, signs and paint. Anything unclear counts as
construction.

**Keeping it current:** a monthly GitHub Actions check (`pipeline/check_freshness.py`) opens an
issue when a new full year of crash data is available, a council term has ended, or a linked plan
stops opening. It doesn't rebuild the site, because each of those needs a person to review it.

## 2026-10 — Earlier choices

- **Years:** pages default to 2023 onward. San Mateo Police reports from August 2021 through
  July 2022 are missing from the state data. 2016 is left out because nearly all of that year's
  San Mateo Police reports are missing. The current year is shown only once complete.
- **Who counts:** injured passengers listed as "witness" in the injured-persons file are counted,
  since the officer's crash totals include them. Stand-up scooters are their own group; mopeds stay
  "in a vehicle." Freeway crashes are left out.
- **Locations:** a crash whose coordinates are more than 200 m from the streets named in its
  report is placed from the street description instead.
- **Deaths:** only month, year and how the person was traveling are shown; no age or sex.
- **URL:** the site lives at `/san-mateo-crashes/` because `/crashes/` on maxmautner.com is a
  permanent redirect to a blog post and must keep working.
- **Contact:** removal and error requests go to movesanmateo@gmail.com.
