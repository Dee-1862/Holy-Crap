# Holy-Crap Console

Next.js 16 + React 19 + TypeScript. Two routes on filler data:

| Route | What |
|---|---|
| `/` | Desktop console. Health board, summary, specimen feed, specimen card |
| `/m` | Phone version with Overview, Alerts and Specimen tabs |

Style is minimal glassmorphism (sea glass). Tokens and primitives are in `src/app/globals.css`. Fonts are Instrument Serif and Manrope through `next/font`, which needs network access at build time.

## Run

```
cd app/console
npm install
npm run dev        # http://localhost:3000 and /m
npm run build      # production build
npm run lint       # type check
```

## Layout

```
src/app/page.tsx          desktop page
src/app/m/page.tsx        mobile page
src/components/           Gauge, SpecimenCanvas, SpecimenCard, Clock
src/lib/data.ts           filler groups and specimens (synthetic)
src/lib/insight.ts        ranking, status, next step, plain language helpers
src/lib/specimen.ts       placeholder specimen drawing with attention overlay
```

The watch sketch (`app/watch/console/console.ino`) keeps its own copy of the filler data. Keep the two in step until a backend feeds every client.

## Deploy to Vercel

1. Push the repo to GitHub and import it in Vercel.
2. Set **Root Directory** to `app/console`. Framework preset is Next.js and the defaults work.
3. No environment variables are needed while the data is filler.

Nothing has been deployed yet.

## Next

1. Replace `src/lib/data.ts` with a fetch from the backend (REST for history, WebSocket or server sent events for live).
2. Add an offline state and a stale data warning.
3. Replace the drawn placeholder with the stored snapshot and a real Grad-CAM image.
4. Add login before anything real is shown.
