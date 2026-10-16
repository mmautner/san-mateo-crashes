# Stage 1 data report: San Mateo crashes

CCRS files downloaded 2026-10-15 from data.ca.gov (package `ccrs`). City boundary: County of San Mateo GIS, Admin_Features layer 0 (CITY), feature "SAN MATEO". Freeway and street geometry: OpenStreetMap via Overpass. Study area = city limits + 0.5 mile.

## 1. 2023 in detail

### How the count is built

| Step | Crashes | People hurt |
|---|---:|---:|
| Reports with City Name = San Mateo (any road) | 968 | 515 (walking 46, biking 22, scooters 2, in vehicles 445; killed 3, serious 26, other 486) |
| Located inside city limits (any road) | 962 | 505 (walking 45, biking 21, scooters 2, in vehicles 437; killed 3, serious 26, other 476) |
| Located inside city limits, freeways and ramps removed | 438 | 307 (walking 44, biking 21, scooters 2, in vehicles 240; killed 0, serious 17, other 290) |
| City + 0.5 mi buffer (any road) | 1229 | 613 (walking 51, biking 28, scooters 4, in vehicles 530; killed 4, serious 31, other 578) |
| **City + 0.5 mi buffer, freeways and ramps removed (what the tool uses)** | 610 | 381 (walking 50, biking 28, scooters 4, in vehicles 299; killed 0, serious 20, other 361) |

Freeway exclusion removes **619 crashes** in the study area and **232 people hurt** (4 killed). The 0.5-mile buffer adds 172 surface-street crashes from neighboring cities.

Crashes in the buffer by reported city: San Mateo 433, Foster City 55, Belmont 55, Burlingame 30, Hillsborough 22, Unincorporated 9, Tiburon 4, Berkeley 1, Redwood City 1

### Comparison with OTS (292 killed or injured in San Mateo city, 2023)

- City Name = San Mateo, all roads: 515 people (crash-level NumberInjured+NumberKilled = 515; excluding witness-flagged = 508)
- …reported by San Mateo Police (NCIC 4116): 307 people (crash-level NumberInjured+NumberKilled = 307; excluding witness-flagged = 300)
- …reported by CHP (NCIC 93xx): 208 people (crash-level NumberInjured+NumberKilled = 208; excluding witness-flagged = 208)
- City Name = San Mateo, freeways removed: 312 people (crash-level NumberInjured+NumberKilled = 312; excluding witness-flagged = 305)
- Inside city limits by location, freeways removed: 307 people (crash-level NumberInjured+NumberKilled = 307; excluding witness-flagged = 300)

### People with an injury recorded but flagged witness-only (2023, tool area): 7

- crash 2029906: SuspectMinor, person type 'Passenger', party /; crash total injured 2; S DELAWARE STREET & CONCAR DRIVE
- crash 2047067: PossibleInjury, person type 'Passenger', party /; crash total injured 3; E POPLAR AV & N HUMBOLDT STREET
- crash 2044675: SuspectMinor, person type 'Passenger', party Driver/PassengerCarStationWagonJeep; crash total injured 6; S CLAREMONT ST & 1ST AVENUE
- crash 2044675: SuspectMinor, person type 'Passenger', party Driver/PassengerCarStationWagonJeep; crash total injured 6; S CLAREMONT ST & 1ST AVENUE
- crash 2044675: SuspectMinor, person type 'Passenger', party Driver/PassengerCarStationWagonJeep; crash total injured 6; S CLAREMONT ST & 1ST AVENUE
- crash 2044675: SuspectSerious, person type 'Passenger', party Driver/PassengerCarStationWagonJeep; crash total injured 6; S CLAREMONT ST & 1ST AVENUE
- crash 2230490: SuspectMinor, person type 'Passenger', party /; crash total injured 2; S EL CAMINO REAL & E 16TH AV

### Field values used (2023, tool area)

Injury severity (`ExtentOfInjuryCode`):

- `SuspectMinor` → other: 267
- `PossibleInjury` → other: 91
- `SuspectSerious` → serious: 20
- `OtherVisibleInactive` → other: 3
- blank → not counted (witness or uninjured): 378 person rows

Mode (`InjuredPersonType`, then the person's party `PartyType` / `Vehicle1TypeDesc`):

- Driver / Driver / PassengerCarStationWagonJeep → vehicle: 173
- Passenger / Driver / PassengerCarStationWagonJeep → vehicle: 52
- Pedestrian / Pedestrian / Pedestrian → walk: 50
- Bicyclist / Bicyclist / Bicycle → bike: 27
- Driver / Driver / SportUtilityVehicle → vehicle: 22
- Driver / Driver / Motorcycle → vehicle: 11
- Passenger / Driver / SportUtilityVehicle → vehicle: 7
- Driver / Driver / MotorDrivenCycleScooter15HpOrLess → vehicle: 4
- Driver / Driver / PickupsAndPanels → vehicle: 4
- Passenger /  / (blank) → vehicle: 3
- Driver / Driver / MiniVan → vehicle: 3
- Driver / Driver / OtherCommercial → vehicle: 3
- Driver / Driver / GoPedZipElectricScooterAndMotorboard → scooter: 3
- Passenger / Driver / MiniVan → vehicle: 3
- Passenger / ParkedVehicle / PassengerCarStationWagonJeep → vehicle: 2
- Other / ParkedVehicle / PassengerCarStationWagonJeep → vehicle: 2
- Driver / Driver / HmPickupAndPanelTruck → vehicle: 1
- Other / Other / NonCommercialBus → vehicle: 1
- Passenger / Driver / OtherCommercial → vehicle: 1
- Driver / Driver / TwoAxleTruck → vehicle: 1
- Passenger / Driver / PickupsAndPanels → vehicle: 1
- Other / Other / MotorDrivenCycleScooter15HpOrLess → vehicle: 1
- Driver / Driver / HmwPassengerCarStationWagonJeep → vehicle: 1
- Other / Other / MotorizedBicycle → bike: 1
- Driver / Driver / EmergencyVehicleOnEmergencyRunOrPursuit → vehicle: 1
- Driver / Driver / (blank) → vehicle: 1
- Passenger / Driver / (blank) → vehicle: 1
- Other / Other / GoPedZipElectricScooterAndMotorboard → scooter: 1

## 2. All years (study area, freeways removed)

| Year | Crashes kept | People hurt | Walking | Biking | In vehicles | Killed | Serious | Freeway crashes removed | No coords (SM + neighbors) | …placed from street names | …unplaced, City Name = San Mateo | Downloaded |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2016 | 242 | 95 | 9 | 8 | 78 | 0 | 2 | 416 | 669 | 48 | 191 | 2026-10-15 |
| 2017 | 707 | 414 | 61 | 36 | 317 | 3 | 18 | 591 | 405 | 77 | 145 | 2026-10-15 |
| 2018 | 743 | 438 | 64 | 43 | 331 | 2 | 26 | 659 | 140 | 95 | 35 | 2026-10-15 |
| 2019 | 714 | 377 | 58 | 26 | 292 | 1 | 22 | 694 | 97 | 89 | 40 | 2026-10-15 |
| 2020 | 490 | 273 | 37 | 32 | 204 | 3 | 13 | 406 | 69 | 51 | 20 | 2026-10-15 |
| 2021 | 361 | 200 | 18 | 20 | 161 | 1 | 14 | 611 | 66 | 36 | 7 | 2026-10-15 |
| 2022 | 317 | 184 | 19 | 21 | 144 | 2 | 7 | 601 | 50 | 34 | 2 | 2026-10-15 |
| 2023 | 610 | 381 | 50 | 28 | 299 | 0 | 20 | 619 | 36 | 38 | 3 | 2026-10-15 |
| 2024 | 649 | 411 | 49 | 51 | 309 | 2 | 16 | 628 | 37 | 36 | 2 | 2026-10-15 |
| 2025 | 502 | 362 | 50 | 35 | 274 | 3 | 21 | 580 | 41 | 24 | 1 | 2026-10-15 |

2025 people hurt = 362 vs 2023–2024 average 396 (-9%).

### Reporting gaps by agency (crash reports per month)

| Year | San Mateo PD reports | months with ≤3 | CHP reports (City Name = San Mateo) | Belmont | Foster City | Burlingame | Hillsborough |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2016 | 33 | 9 (1,2,4,5,6,7,8,9,12) | 547 | 147 | 133 | 116 | 59 |
| 2017 | 503 | 0 | 620 | 138 | 96 | 144 | 40 |
| 2018 | 545 | 0 | 603 | 127 | 90 | 130 | 58 |
| 2019 | 548 | 0 | 623 | 120 | 106 | 87 | 37 |
| 2020 | 386 | 0 | 344 | 122 | 67 | 51 | 2 |
| 2021 | 218 | 5 (8,9,10,11,12) | 545 | 163 | 80 | 53 | 7 |
| 2022 | 141 | 7 (1,2,3,4,5,6,7) | 512 | 167 | 94 | 55 | 26 |
| 2023 | 428 | 0 | 540 | 141 | 94 | 103 | 35 |
| 2024 | 449 | 0 | 534 | 104 | 108 | 110 | 33 |
| 2025 | 342 | 0 | 501 | 91 | 113 | 59 | 0 |

### Missing coordinates

- 2016: City Name = San Mateo missing coordinates: 199 of 580 (34.3%); all nearby-city reports missing coordinates: 669, placed from street names and inside study area: 48
- 2017: City Name = San Mateo missing coordinates: 158 of 1124 (14.1%); all nearby-city reports missing coordinates: 405, placed from street names and inside study area: 77
- 2018: City Name = San Mateo missing coordinates: 61 of 1148 (5.3%); all nearby-city reports missing coordinates: 140, placed from street names and inside study area: 95
- 2019: City Name = San Mateo missing coordinates: 57 of 1172 (4.9%); all nearby-city reports missing coordinates: 97, placed from street names and inside study area: 89
- 2020: City Name = San Mateo missing coordinates: 29 of 730 (4.0%); all nearby-city reports missing coordinates: 69, placed from street names and inside study area: 51
- 2021: City Name = San Mateo missing coordinates: 10 of 767 (1.3%); all nearby-city reports missing coordinates: 66, placed from street names and inside study area: 36
- 2022: City Name = San Mateo missing coordinates: 3 of 653 (0.5%); all nearby-city reports missing coordinates: 50, placed from street names and inside study area: 34
- 2023: City Name = San Mateo missing coordinates: 4 of 968 (0.4%); all nearby-city reports missing coordinates: 36, placed from street names and inside study area: 38
- 2024: City Name = San Mateo missing coordinates: 3 of 983 (0.3%); all nearby-city reports missing coordinates: 37, placed from street names and inside study area: 36
- 2025: City Name = San Mateo missing coordinates: 1 of 843 (0.1%); all nearby-city reports missing coordinates: 41, placed from street names and inside study area: 24

Unplaced San Mateo reports (2021–2025) with anyone hurt:

- 6/30/2021  CLARKE AV & RUNNYMEDE ST: 1 (walking 0, biking 1, scooters 0, in vehicles 0; killed 0, serious 0, other 1); freeway=False
- 3/24/2022  ROAD 1 HORSESHOE & REFERNCE POINT: 1 (walking 0, biking 0, scooters 0, in vehicles 1; killed 0, serious 0, other 1); freeway=False
- 3/31/2022  RT 1 & PILLAR ITB TERMINAL ARRIVAL: 1 (walking 0, biking 0, scooters 0, in vehicles 1; killed 0, serious 0, other 1); freeway=False
- 8/9/2023 1 N EL CAMINO REAL & TILTON AVE: 1 (walking 0, biking 0, scooters 0, in vehicles 1; killed 0, serious 0, other 1); freeway=False
- 5/3/2024 1 4007 BAYVIEW AV & 40TH AVE: 1 (walking 0, biking 0, scooters 0, in vehicles 1; killed 0, serious 0, other 1); freeway=False
- 11/29/2025 UPPER INTL CENTER ISLAND & INTL DEPARTURES: 1 (walking 1, biking 0, scooters 0, in vehicles 0; killed 0, serious 0, other 1); freeway=False

## 3. Intersections at default settings (0.25 mile, 2023–2025)

1414 intersections inside city limits (OSM nodes where two differently named streets meet; same-name pairs within 60 m merged).

- median: **10** people hurt within 0.25 mi
- 25th percentile: 4; 75th: **26**; 90th: **41**; max: 96
- share with zero: **6.2%**; with 1–4: 22.7%
- total people hurt in study area 2023–2025 (freeways removed): 1154

Top 15:

| # | Intersection | People hurt | Walking | Biking | In vehicles | Killed |
|---:|---|---:|---:|---:|---:|---:|
| 1 | East 3rd Avenue & South Ellsworth Avenue | 96 | 25 | 7 | 63 | 0 |
| 2 | 2nd Avenue & South Ellsworth Avenue | 93 | 24 | 8 | 60 | 0 |
| 3 | 1st Avenue & South Ellsworth Avenue | 82 | 19 | 7 | 55 | 0 |
| 4 | 1st Avenue & South B Street | 81 | 21 | 10 | 49 | 0 |
| 5 | East 4th Avenue & South Ellsworth Avenue | 81 | 24 | 6 | 50 | 0 |
| 6 | South San Mateo Drive & 2nd Avenue | 80 | 21 | 6 | 52 | 0 |
| 7 | South El Camino Real & Crystal Springs Road | 79 | 18 | 5 | 56 | 0 |
| 8 | North San Mateo Drive & Baldwin Avenue | 79 | 12 | 8 | 58 | 0 |
| 9 | East 3rd Avenue & South San Mateo Drive | 79 | 22 | 6 | 50 | 0 |
| 10 | Monte Diablo Avenue & North Ellsworth Avenue | 78 | 14 | 9 | 55 | 0 |
| 11 | East 4th Avenue & South B Street | 78 | 23 | 6 | 48 | 0 |
| 12 | East 3rd Avenue & South B Street | 78 | 23 | 7 | 47 | 0 |
| 13 | East 5th Avenue & South Ellsworth Avenue | 77 | 23 | 5 | 48 | 0 |
| 14 | 2nd Avenue & South Railroad Avenue | 76 | 22 | 10 | 43 | 0 |
| 15 | East 4th Avenue & South San Mateo Drive | 75 | 22 | 5 | 47 | 0 |

Test intersection Alameda de las Pulgas & Aragon Boulevard: 5 people (walking 0, biking 1, in vehicles 4, killed 0); more than 29% of intersections

Test intersection North San Mateo Drive & Monte Diablo Avenue: 66 people (walking 9, biking 8, in vehicles 49, killed 0); more than 97% of intersections

## 4. Coordinates vs. street descriptions

Of 1761 located crashes 2023–2025, 1005 have street names that match an OSM intersection. Distance from the reported coordinates to that intersection, minus the stated offset:

- within 25 m: 70.0%
- within 50 m: 82.4%
- within 100 m: 92.0%
- within 200 m: 99.9%
- within 400 m: 99.9%

Five randomly chosen crashes (seed 2023):

- **2/29/2024 **, report says *CALIFORNIA DR* & *NORTH LN*, at the intersection. Coordinates 37.57997, -122.34585 are 8 m from OSM California Drive & North Lane.
- **1/16/2025 **, report says *PARK RD* & *HOWARD AV*, 208 F S. Coordinates 37.57724, -122.34568 are 2 m from OSM Howard Avenue & Park Road.
- **12/18/2025**, report says *S EL CAMINO REAL* & *23RD AVE*, at the intersection. Coordinates 37.54568, -122.30744 are 41 m from OSM South El Camino Real & 23rd Avenue.
- **5/22/2024 **, report says *S NORFOLK ST* & *E HILLSDALE BLVD*, 41 F S. Coordinates 37.54623, -122.28516 are 14 m from OSM East Hillsdale Boulevard & South Norfolk Street.
- **8/28/2025 **, report says *TILTON AV* & *N DELAWARE ST*, 5 F N. Coordinates 37.57097, -122.32426 are 2 m from OSM North Delaware Street & Tilton Avenue.

Largest mismatches (1 over 200 m):

- 9/5/2023 4 NORTH EL CAMINO REAL & WEST BELLEVUE AVENUE: 1964 m from the intersection, stated offset 0 m
