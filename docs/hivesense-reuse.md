# HiveSense reuse notes

HiveSense (https://github.com/Dee-1862/HiveSense) is an earlier project in the same GitHub account. A copy is cloned at `cloner/HiveSense` for reference. It has no license file, and it is a Python backend (Fetch.ai agents, acoustic and vision models) with a Vite and Leaflet frontend.

## What we took
The dashboard pattern, not the code. The Holy-Crap console is written fresh in `app/console` with its own components, data model and visual design.

| Idea from HiveSense | Our version |
|---|---|
| Header with headline numbers and a live link badge | Barn index, groups, open alerts and a demo data badge |
| Site map with a marker per unit and filter chips | `SiteMap.tsx`, an SVG floor plan of pens with bird dots, a camera cone and specimen pins |
| Hive readout with a radar chart and a recommended plan | `Readout.tsx` and `Radar.tsx` over five specimen scores |
| Live ticker along the bottom | `Ticker.tsx` |
| Honest evaluation by held-out colony | Same principle in our plan, split by source rather than at random (see paper-plan.md) |

## What we did not copy
- No HiveSense source files, styles or media are in `app/`.
- The look is different on purpose (sea glass, green and yellow and red status colors), and the domain is different (droppings, not bees).

## Disclosure
The team should say plainly that the dashboard layout was adapted from our earlier HiveSense project. The hackathon rules decide how much pre-existing work is allowed, so check them before submitting. Hiding the connection from judges is not something this repo should do, and it is also easy to get caught on, since judges who know HiveSense will recognise the layout. Crediting it costs nothing and shows reuse of our own tooling, which is normal.

## Possible next reuse (with credit)
- The HiveSense API server and live feed ideas could inspire our backend event stream.
- The tunnel camera mounting idea in `hardware/` is close to our fixed camera over a manure belt.
- Their validation write-up is a good model for our evaluation section.

## Housekeeping
`cloner/` holds a nested git repo, so it is ignored by this repo (see `.gitignore`). Delete it any time. Do not commit its contents unless the team decides to vendor part of it, with credit.
