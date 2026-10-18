# UI Design (web, mobile, watch)

Prototype status 2026-10-17. All three UIs run on filler data (synthetic, not model output). Nothing talks to the backend yet.

## Look
- Minimal glassmorphism in the spirit of Apple glass. Two themes. Light is a simple blue on blue backdrop with soft white glass and navy ink. Dark is black with white glass. It follows the system setting and the header toggle overrides it.
- Panels have no solid white border. A 1px rim fades from a bright top left corner through clear to a faint bottom right, like light catching glass edges.
- Ink is navy in light mode and near white in dark mode. Status colors are green for healthy, golden yellow for normal but watch and red for critical, with slightly brighter values in dark mode. Yellow replaced the earlier tangerine so it reads calm, and red is reserved for real alerts. The earlier aqua, peach and orange backdrop colors are gone.
- Fonts are Instrument Serif for headlines and grade numerals and Manrope for text, loaded with next/font.
- Memorable element is the circular grade gauge with a serif numeral.
- Motion is limited to the slow background drift and the gauge fill. Both respect reduced motion.

## Three clients, one data model
| Client | Where | Role |
|---|---|---|
| Web console | `app/console` route `/` | Health board, summary, specimen feed and specimen card with next step, evidence and scores |
| Mobile | `app/console` route `/m` | Phone first. Three tabs for Overview, Alerts and Specimen. Large touch targets |
| StopWatch | `app/watch/console/console.ino` | Glance view with a health board and group screens driven by the buttons |

Web and mobile are one Next.js 16 + React 19 + TypeScript project in `app/console`, ready for Vercel (see its README). Filler data is in `src/lib/data.ts`. The watch keeps its own copy of the data inside the sketch. Keep them in step until the backend feeds all three.

## Specimen card and grade
- The card shows a grade from 1 to 10, the suspected type with confidence, five sub-scores (color, consistency, urate cap, blood or mucus, foam) and a screening disclaimer.
- Grade is provisional. In the demo it comes from the model's healthy probability, lowered by abnormal cues. It has not been validated against any veterinary scale. A real definition needs labeled data for the sub-scores, since the Machuve set only has disease labels.
- Disease names appear as "Suspected ..." with confidence. They are appearance-based screening hints and a lab test confirms a diagnosis. This differs from the earlier normal or abnormal only plan, and the team should confirm it is acceptable.

## Explainability panel
- Class probabilities as bars, with an uncertainty note from the margin between the top two classes.
- Attention map toggle over the specimen image. In production this is a Grad-CAM style heatmap computed by the backend on the stored snapshot, not on the Pi.
- Evidence list in plain language ("firm shape with a distinct white cap").
- Closest reference examples from the training set (placeholders in the demo).
- A short note on how the grade works.

## Actions (same on all three)
| Action | Web and mobile | Watch |
|---|---|---|
| Acknowledge | button | A click |
| False alarm | button | A hold |
| Call the vet | hold the button about 1.5 s | B hold about 1.5 s with a progress ring, then red flashes reading TERMINATED and a final screen reading VET CALLED |

Calling the vet is a notification to a person. The button never culls anything. The flashing word TERMINATED is dramatic styling, and the final screen says VET CALLED so the real effect is clear. There is no cull action anywhere. In the demo nothing is sent.

## Watch controls
The watch uses the two buttons, with touch as a backup. Any press wakes the screen after it sleeps (20 s idle), and the waking press does nothing else.
- Health board (home): groups ranked by mean grade of the last 15 minutes, healthiest first. Rows touch each other with no gaps and no marker box at the start. A moves the highlight down, B opens the group.
- Group screen: specimen photo, grade, confidence, group stats. A shows the next specimen, A hold opens the menu (acknowledge, false alarm, cancel), B goes back, B hold calls the vet.
- Photos are placeholders from `app/watch/console/specimens.h`, made by `app/tools/make_watch_images.py`. Real photos can replace them (see the script header).
- Live photos later: the backend sends a small JPEG (about 180 by 135, roughly 4 to 10 KB) per specimen over HTTP and the watch draws it with `drawJpg`. Not built yet.

## Next
1. Replace filler data with the backend feed (WebSocket for web and mobile, MQTT for the watch).
2. Add the offline state to all three.
3. Real Grad-CAM images from the backend.
4. Decide the grade definition and where the sub-scores come from.

## Actions and watch screens (2026-10-17)
Button names say what they do. Each has a one line caption in the apps.
| Name | What it does | Caption |
|---|---|---|
| I'll check it | Marks the specimen as being checked, visible to everyone | Tells the team you are on it |
| Looks normal | Marks it normal and removes it from alerts and averages. Can be undone | Removes it from alerts |
| Call the vet | Hold to send. Logs a vet request, optionally to a webhook. One request per pen per minute | Hold to send |

Real phone calls are on hold. The apps say plainly when a request was only saved.

Watch screens: Active, Overview (barn health ring and a bar per pen), Health board, Pen pages and an action menu. Each specimen has a photo page with numbered markers and a Why page with class probabilities and the numbered evidence lines. The last pen page is a score radar. The photo and Why pages are the explainability view.

## Plain language update (2026-10-17)
- The radar chart is gone. A pen and each specimen now show a short checklist, "What we checked": Color, Firmness, White cap, Blood or mucus and Foam, each with a word (Normal, Soft, Watery, Missing, Seen, None) and a colored dot. A scores of 8 or more reads as normal, 5 to 7 as a bit off, under 5 as a problem. One sentence sums it up, for example "Mostly blood or mucus and color are off."
- Confidence is said in words (Very sure, Fairly sure, Not sure), with the percentage kept next to it on the web.
- Watch "Why this result" no longer shows four class bars. It names the most likely result, how sure the model is in three dots, a second possibility only when it is at least 15 percent, and the numbered evidence lines.
- Watch start screen shows the barn health ring, one status strip with the number of healthy, need a look and urgent pens, and the pen to check first. The full list of pens stays on the health board.
