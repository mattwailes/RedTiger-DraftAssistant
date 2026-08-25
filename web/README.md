# RedTiger Draft Board (web)

An interactive draft-day recommender: upload blended projections, tune
scoring rules live (need / tier cliffs / bye conflicts), and get a
next-best-pick recommendation with a plain-English breakdown.

## Run it locally

```bash
cd web
npm install
npm run dev
```

Opens at http://localhost:5173. Loaded with sample data so it works
immediately — use the CSV upload controls in the "Projection sources"
panel to load your real FantasyPros/ESPN/Yahoo exports. Expected columns:

```
player,team,position,proj_points,bye_week
```

## Deploying

`npm run build` produces a static `dist/` folder — deployable to GitHub
Pages, Vercel, Netlify, or any static host. Everything except the "Ask
Claude why" button works with zero backend.

## The "Ask Claude why" button

This calls out to Claude for a plain-English gut check on the top
candidates. Browsers can't safely hold an Anthropic API key, and
`api.anthropic.com` only accepts direct browser requests from inside
Claude.ai's own artifact sandbox — so a standalone deployment needs a
tiny backend proxy that holds the key server-side.

Minimal example (Node/Express):

```js
// server.js
import express from "express";
const app = express();
app.use(express.json());

app.post("/api/ai-advisor", async (req, res) => {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(req.body),
  });
  res.json(await r.json());
});

app.listen(3000);
```

Then set `VITE_AI_PROXY_URL=http://localhost:3000/api/ai-advisor` in a
`.env` file before `npm run dev` / `npm run build`. If you skip this,
the button will just tell you it isn't configured — everything else on
the page works fine without it.
