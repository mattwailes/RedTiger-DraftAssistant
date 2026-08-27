import React, { useState, useMemo, useCallback, useRef } from "react";
import Papa from "papaparse";
import {
  Upload, TrendingUp, AlertTriangle, Check, X, Sparkles,
  Users, Calendar, ChevronRight, Trash2, Sliders, Loader2
} from "lucide-react";

/* ---------------------------------------------------------------
   Design tokens — "War Room" theme: turf green + chalkboard,
   scoreboard-condensed numerals for stats, gold accent for the CTA.
----------------------------------------------------------------*/
const FONTS = `
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');
`;

const COLORS = {
  bg: "#0B0B0B",
  panel: "#171717",
  panelLight: "#242424",
  chalk: "#FFFFFF",
  chalkDim: "#B8B8B8",
  line: "#3A3A3A",
  gold: "#FB4F14",
  amber: "#FF6A2A",
  red: "#FB4F14",
  blue: "#D8D8D8",
};

const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"];
const FLEX_ELIGIBLE = ["RB", "WR", "TE"];

const DEFAULT_ROSTER_SPOTS = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1 };

/* ---------------------------------------------------------------
   Sample data so the page is usable the instant it loads
----------------------------------------------------------------*/
const SAMPLE_FANTASYPROS = [
  ["Christian McCaffrey", "SF", "RB", 310.5, 9],
  ["Bijan Robinson", "ATL", "RB", 295.2, 12],
  ["CeeDee Lamb", "DAL", "WR", 288.0, 7],
  ["Tyreek Hill", "MIA", "WR", 280.4, 6],
  ["Breece Hall", "NYJ", "RB", 275.0, 12],
  ["Ja'Marr Chase", "CIN", "WR", 270.8, 12],
  ["Justin Jefferson", "MIN", "WR", 268.5, 6],
  ["Josh Allen", "BUF", "QB", 395.0, 12],
  ["Jahmyr Gibbs", "DET", "RB", 260.0, 9],
  ["Amon-Ra St. Brown", "DET", "WR", 258.0, 9],
  ["Patrick Mahomes", "KC", "QB", 380.5, 6],
  ["Travis Kelce", "KC", "TE", 220.0, 6],
  ["Sam LaPorta", "DET", "TE", 195.0, 9],
  ["Saquon Barkley", "PHI", "RB", 255.0, 5],
  ["Puka Nacua", "LAR", "WR", 240.0, 6],
  ["Lamar Jackson", "BAL", "QB", 375.0, 14],
  ["De'Von Achane", "MIA", "RB", 230.0, 6],
  ["A.J. Brown", "PHI", "WR", 235.0, 5],
  ["Mark Andrews", "BAL", "TE", 175.0, 14],
  ["Chris Olave", "NO", "WR", 220.0, 11],
].map(([player, team, position, proj_points, bye_week]) => ({
  player, team, position, proj_points, bye_week,
}));

const SAMPLE_ESPN = SAMPLE_FANTASYPROS.map((p) => ({
  ...p,
  proj_points: Math.round((p.proj_points - 4 + Math.random() * 8) * 10) / 10,
}));

/* ---------------------------------------------------------------
   Helpers
----------------------------------------------------------------*/
function normalizeName(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[.'-]/g, "")
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function blendSources(sources) {
  // sources: [{ name, weight, rows: [{player,team,position,proj_points,bye_week}] }]
  const active = sources.filter((s) => s.rows.length > 0);
  const totalWeight = active.reduce((sum, s) => sum + s.weight, 0) || 1;

  const byName = new Map();
  for (const source of active) {
    const w = source.weight / totalWeight;
    for (const row of source.rows) {
      const key = normalizeName(row.player);
      if (!key) continue;
      if (!byName.has(key)) {
        byName.set(key, {
          player: row.player,
          team: row.team,
          position: (row.position || "").toUpperCase(),
          bye_week: row.bye_week ?? null,
          weightedSum: 0,
          weightCovered: 0,
        });
      }
      const entry = byName.get(key);
      entry.weightedSum += (Number(row.proj_points) || 0) * w;
      entry.weightCovered += w;
      if (entry.bye_week == null && row.bye_week != null) entry.bye_week = row.bye_week;
    }
  }

  return Array.from(byName.values()).map((e) => ({
    player: e.player,
    team: e.team,
    position: e.position,
    bye_week: e.bye_week,
    proj_points: e.weightCovered > 0 ? e.weightedSum / e.weightCovered : 0,
  }));
}

function computeBaselines(players, rosterSpots, numTeams) {
  const flexSpots = rosterSpots.FLEX || 0;
  const flexShare = flexSpots ? flexSpots / FLEX_ELIGIBLE.length : 0;
  const baselines = {};
  for (const pos of POSITIONS) {
    const starters = rosterSpots[pos] || 0;
    let n = starters * numTeams;
    if (FLEX_ELIGIBLE.includes(pos)) n += Math.round(flexShare * numTeams);
    const posPlayers = players
      .filter((p) => p.position === pos)
      .sort((a, b) => b.proj_points - a.proj_points);
    if (posPlayers.length >= n && n > 0) baselines[pos] = posPlayers[n - 1].proj_points;
    else if (posPlayers.length) baselines[pos] = posPlayers[posPlayers.length - 1].proj_points;
    else baselines[pos] = 0;
  }
  return baselines;
}

function targetCount(pos, rosterSpots, numTeams) {
  const starters = rosterSpots[pos] || 0;
  const flexSpots = rosterSpots.FLEX || 0;
  const flexShare = FLEX_ELIGIBLE.includes(pos) && flexSpots ? flexSpots / FLEX_ELIGIBLE.length : 0;
  return starters + flexShare;
}

/* ---------------------------------------------------------------
   Main component
----------------------------------------------------------------*/
export default function DraftBoard() {
  const [sources, setSources] = useState([
    { id: "fantasypros", name: "FantasyPros", weight: 0.5, rows: SAMPLE_FANTASYPROS },
    { id: "espn", name: "ESPN", weight: 0.5, rows: SAMPLE_ESPN },
  ]);
  const [numTeams, setNumTeams] = useState(12);
  const [rosterSpots, setRosterSpots] = useState(DEFAULT_ROSTER_SPOTS);
  const [weights, setWeights] = useState({ need: 1, tier: 1, bye: 1 });
  const [draftedNames, setDraftedNames] = useState(new Set());
  const [yourRoster, setYourRoster] = useState([]);
  const [posFilter, setPosFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [aiNote, setAiNote] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const fileInputRef = useRef(null);
  const [pendingSourceId, setPendingSourceId] = useState(null);

  /* ---- derived data ---- */
  const blended = useMemo(() => blendSources(sources), [sources]);
  const baselines = useMemo(
    () => computeBaselines(blended, rosterSpots, numTeams),
    [blended, rosterSpots, numTeams]
  );
  const withVbd = useMemo(
    () =>
      blended
        .map((p) => ({ ...p, vbd: p.proj_points - (baselines[p.position] || 0) }))
        .sort((a, b) => b.vbd - a.vbd),
    [blended, baselines]
  );
  const available = useMemo(
    () => withVbd.filter((p) => !draftedNames.has(normalizeName(p.player))),
    [withVbd, draftedNames]
  );

  const rosterCounts = useMemo(() => {
    const counts = {};
    for (const p of yourRoster) counts[p.position] = (counts[p.position] || 0) + 1;
    return counts;
  }, [yourRoster]);

  const rosterByeWeeks = useMemo(() => {
    const map = {};
    for (const p of yourRoster) {
      if (p.bye_week == null) continue;
      if (!map[p.bye_week]) map[p.bye_week] = [];
      map[p.bye_week].push(p);
    }
    return map;
  }, [yourRoster]);

  // tier gap per position (for cliff bonus)
  const tierGaps = useMemo(() => {
    const gaps = {};
    for (const pos of POSITIONS) {
      const list = available.filter((p) => p.position === pos);
      const posGaps = list.map((p, i) =>
        i < list.length - 1 ? p.vbd - list[i + 1].vbd : 0
      );
      const avg = posGaps.length ? posGaps.reduce((a, b) => a + b, 0) / posGaps.length : 0;
      list.forEach((p, i) => {
        gaps[normalizeName(p.player)] = Math.max(0, (posGaps[i] || 0) - avg);
      });
    }
    return gaps;
  }, [available]);

  const scored = useMemo(() => {
    return available.map((p) => {
      const target = targetCount(p.position, rosterSpots, numTeams);
      const filled = rosterCounts[p.position] || 0;
      const remaining = target - filled;
      const needMultBase = remaining > 0 ? 1.15 : 0.95;
      const needMult = 1 + (needMultBase - 1) * weights.need;

      const tierBonus = (tierGaps[normalizeName(p.player)] || 0) * weights.tier * 0.5;

      const byeConflicts =
        p.bye_week != null ? (rosterByeWeeks[p.bye_week] || []).length : 0;
      const byePenalty = byeConflicts * 8 * weights.bye;

      const score = p.vbd * needMult + tierBonus - byePenalty;

      return {
        ...p,
        score,
        needMult,
        tierBonus,
        byeConflicts,
        byePenalty,
        remaining,
      };
    }).sort((a, b) => b.score - a.score);
  }, [available, rosterCounts, rosterByeWeeks, tierGaps, weights, rosterSpots, numTeams]);

  const topPick = scored[0];
  const runnersUp = scored.slice(1, 4);

  const filteredTable = useMemo(() => {
    return scored.filter((p) => {
      if (posFilter !== "ALL" && p.position !== posFilter) return false;
      if (search && !p.player.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [scored, posFilter, search]);

  /* ---- actions ---- */
  const draftPlayer = useCallback((player, mine) => {
    setDraftedNames((prev) => {
      const next = new Set(prev);
      next.add(normalizeName(player.player));
      return next;
    });
    if (mine) setYourRoster((prev) => [...prev, player]);
    setAiNote("");
  }, []);

  const undraftAll = useCallback(() => {
    setDraftedNames(new Set());
    setYourRoster([]);
    setAiNote("");
  }, []);

  const triggerUpload = (sourceId) => {
    setPendingSourceId(sourceId);
    fileInputRef.current?.click();
  };

  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (!file || !pendingSourceId) return;
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const rows = results.data
          .map((r) => {
            const norm = {};
            for (const k of Object.keys(r)) norm[k.trim().toLowerCase()] = r[k];
            return {
              player: norm.player,
              team: (norm.team || "").toUpperCase(),
              position: (norm.position || "").toUpperCase(),
              proj_points: Number(norm.proj_points),
              bye_week: norm.bye_week ? Number(norm.bye_week) : null,
            };
          })
          .filter((r) => r.player && !isNaN(r.proj_points));
        setSources((prev) =>
          prev.map((s) => (s.id === pendingSourceId ? { ...s, rows } : s))
        );
      },
    });
    e.target.value = "";
    setPendingSourceId(null);
  };

  const updateWeight = (id, w) => {
    setSources((prev) => prev.map((s) => (s.id === id ? { ...s, weight: w } : s)));
  };

  const askClaude = async () => {
    if (!topPick) return;
    setAiLoading(true);
    setAiNote("");
    try {
      const context = {
        top_candidates: scored.slice(0, 5).map((p) => ({
          player: p.player,
          position: p.position,
          team: p.team,
          vbd: Math.round(p.vbd * 10) / 10,
          score: Math.round(p.score * 10) / 10,
          bye_week: p.bye_week,
          bye_conflicts: p.byeConflicts,
          still_needed: p.remaining > 0,
        })),
        your_roster: yourRoster.map((p) => ({ player: p.player, position: p.position, bye_week: p.bye_week })),
      };
      // NOTE: this calls YOUR OWN backend proxy, not Anthropic directly.
      // Browsers can't safely hold an Anthropic API key, and api.anthropic.com
      // doesn't allow direct browser calls outside Claude.ai's artifact sandbox.
      // Set VITE_AI_PROXY_URL in a .env file to point at a small server you
      // control that forwards this payload to the Anthropic API with your key.
      // See web/README.md for a minimal example.
      const proxyUrl = import.meta.env.VITE_AI_PROXY_URL;
      if (!proxyUrl) {
        setAiNote(
          "AI advisor isn't configured. Set VITE_AI_PROXY_URL to your backend proxy (see web/README.md)."
        );
        setAiLoading(false);
        return;
      }
      const response = await fetch(proxyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 1000,
          messages: [
            {
              role: "user",
              content: `You are a terse, sharp fantasy football draft advisor. Given this JSON of top available candidates and my current roster, recommend one pick and explain why in 2-3 short sentences. Be direct, mention bye weeks or need if relevant, no fluff.\n\n${JSON.stringify(context, null, 2)}`,
            },
          ],
        }),
      });
      const data = await response.json();
      const text = (data.content || [])
        .map((b) => (b.type === "text" ? b.text : ""))
        .join("\n")
        .trim();
      setAiNote(text || "No response.");
    } catch (err) {
      setAiNote("Couldn't reach the AI advisor right now.");
    } finally {
      setAiLoading(false);
    }
  };

  /* ---------------------------------------------------------------
     Render
  ----------------------------------------------------------------*/
  return (
    <div style={{ background: COLORS.bg, minHeight: "100%", color: COLORS.chalk }}>
      <style>{FONTS}</style>
      <div
        style={{
          fontFamily: "'Inter', sans-serif",
          maxWidth: 1280,
          margin: "0 auto",
          padding: "20px 20px 60px",
        }}
      >
        {/* ---------- Header / settings bar ---------- */}
        <header
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            borderBottom: `2px solid ${COLORS.line}`,
            paddingBottom: 16,
            marginBottom: 20,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: "'Oswald', sans-serif",
                fontSize: 11,
                letterSpacing: "0.25em",
                color: COLORS.gold,
                fontWeight: 600,
              }}
            >
              DRAFT ROOM
            </div>
            <h1
              style={{
                fontFamily: "'Oswald', sans-serif",
                fontSize: 32,
                fontWeight: 700,
                margin: "2px 0 0",
                letterSpacing: "0.01em",
              }}
            >
              Next Best Pick
            </h1>
          </div>

          <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
            <LabeledNumber label="Teams" value={numTeams} onChange={setNumTeams} min={4} max={20} />
            <button
              onClick={undraftAll}
              style={ghostButtonStyle}
              title="Clear all drafted players and your roster"
            >
              <Trash2 size={14} style={{ marginRight: 6 }} />
              Reset draft
            </button>
          </div>
        </header>

        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleFile}
          style={{ display: "none" }}
        />

        <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20 }}>
          {/* ---------- Left column ---------- */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Sources panel */}
            <Panel title="Projection sources" icon={<Upload size={14} />}>
              {sources.map((s) => (
                <div key={s.id} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{s.name}</span>
                    <span style={{ fontSize: 11, color: COLORS.chalkDim, fontFamily: "'IBM Plex Mono', monospace" }}>
                      {s.rows.length} players
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={s.weight}
                      onChange={(e) => updateWeight(s.id, Number(e.target.value))}
                      style={{ flex: 1, accentColor: COLORS.gold }}
                    />
                    <span style={{ fontSize: 11, width: 32, fontFamily: "'IBM Plex Mono', monospace" }}>
                      {Math.round(s.weight * 100)}%
                    </span>
                  </div>
                  <button onClick={() => triggerUpload(s.id)} style={{ ...ghostButtonStyle, fontSize: 11, marginTop: 6, padding: "4px 10px" }}>
                    Upload CSV
                  </button>
                </div>
              ))}
              <div style={{ fontSize: 11, color: COLORS.chalkDim, marginTop: 4, lineHeight: 1.5 }}>
                Columns expected: player, team, position, proj_points, bye_week (optional).
                Loaded with sample data — upload your real exports to replace it.
              </div>
            </Panel>

            {/* Rule weights */}
            <Panel title="Scoring rules" icon={<Sliders size={14} />}>
              <RuleSlider
                label="Positional need"
                hint="Boost players at spots you still need to fill"
                value={weights.need}
                onChange={(v) => setWeights((w) => ({ ...w, need: v }))}
              />
              <RuleSlider
                label="Tier cliffs"
                hint="Boost picks right before a value drop-off"
                value={weights.tier}
                onChange={(v) => setWeights((w) => ({ ...w, tier: v }))}
              />
              <RuleSlider
                label="Bye week conflicts"
                hint="Penalize stacking byes at the same position"
                value={weights.bye}
                onChange={(v) => setWeights((w) => ({ ...w, bye: v }))}
              />
            </Panel>

            {/* Your roster */}
            <Panel title="Your roster" icon={<Users size={14} />}>
              {yourRoster.length === 0 ? (
                <div style={{ fontSize: 12, color: COLORS.chalkDim }}>No picks yet.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {yourRoster.map((p, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: 12,
                        borderBottom: `1px solid ${COLORS.line}`,
                        paddingBottom: 4,
                      }}
                    >
                      <span>
                        <PosBadge pos={p.position} /> {p.player}
                      </span>
                      <span style={{ color: COLORS.chalkDim, fontFamily: "'IBM Plex Mono', monospace" }}>
                        {p.bye_week != null ? `bye ${p.bye_week}` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            {/* Bye week grid */}
            <Panel title="Bye week map" icon={<Calendar size={14} />}>
              {Object.keys(rosterByeWeeks).length === 0 ? (
                <div style={{ fontSize: 12, color: COLORS.chalkDim }}>
                  No bye conflicts to show yet.
                </div>
              ) : (
                Object.entries(rosterByeWeeks)
                  .sort((a, b) => Number(a[0]) - Number(b[0]))
                  .map(([week, players]) => (
                    <div
                      key={week}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: 12,
                        padding: "4px 0",
                        color: players.length > 1 ? COLORS.amber : COLORS.chalk,
                      }}
                    >
                      <span>Week {week}</span>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                        {players.map((p) => p.player.split(" ").slice(-1)[0]).join(", ")}
                        {players.length > 1 ? " ⚠" : ""}
                      </span>
                    </div>
                  ))
              )}
            </Panel>
          </div>

          {/* ---------- Right column ---------- */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Hero: next pick play card */}
            {topPick ? (
              <div
                style={{
                  background: `linear-gradient(135deg, ${COLORS.panelLight}, ${COLORS.panel})`,
                  border: `2px solid ${COLORS.gold}`,
                  borderRadius: 10,
                  padding: 24,
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    top: -20,
                    right: -10,
                    fontFamily: "'Oswald', sans-serif",
                    fontSize: 140,
                    fontWeight: 700,
                    color: "rgba(212,167,61,0.08)",
                    lineHeight: 1,
                  }}
                >
                  {POSITIONS.indexOf(topPick.position) + 1}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", position: "relative" }}>
                  <div>
                    <div style={{ fontSize: 11, letterSpacing: "0.2em", color: COLORS.gold, fontWeight: 600 }}>
                      RECOMMENDED PICK
                    </div>
                    <h2 style={{ fontFamily: "'Oswald', sans-serif", fontSize: 36, fontWeight: 700, margin: "4px 0" }}>
                      {topPick.player}
                    </h2>
                    <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 13, color: COLORS.chalkDim }}>
                      <PosBadge pos={topPick.position} />
                      <span>{topPick.team}</span>
                      {topPick.bye_week != null && <span>Bye {topPick.bye_week}</span>}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 28, fontWeight: 600, color: COLORS.gold }}>
                      {topPick.score.toFixed(1)}
                    </div>
                    <div style={{ fontSize: 10, color: COLORS.chalkDim, letterSpacing: "0.1em" }}>SCORE</div>
                  </div>
                </div>

                {/* reasoning breakdown */}
                <div
                  style={{
                    marginTop: 16,
                    paddingTop: 14,
                    borderTop: `1px dashed ${COLORS.line}`,
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 14,
                    fontSize: 12,
                  }}
                >
                  <ReasonTag label={`+${topPick.vbd.toFixed(1)} VBD`} tone="chalk" />
                  {topPick.remaining > 0 && <ReasonTag label={`Fills open ${topPick.position} spot`} tone="gold" />}
                  {topPick.tierBonus > 1 && <ReasonTag label={`Tier cliff (+${topPick.tierBonus.toFixed(1)})`} tone="blue" />}
                  {topPick.byeConflicts > 0 && (
                    <ReasonTag label={`Bye week ${topPick.bye_week} conflict ×${topPick.byeConflicts}`} tone="amber" />
                  )}
                  {topPick.byeConflicts === 0 && topPick.bye_week != null && (
                    <ReasonTag label="No bye conflict" tone="chalkDim" />
                  )}
                </div>

                <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
                  <button onClick={() => draftPlayer(topPick, true)} style={primaryButtonStyle}>
                    <Check size={14} style={{ marginRight: 6 }} />
                    Draft to my team
                  </button>
                  <button onClick={() => draftPlayer(topPick, false)} style={ghostButtonStyle}>
                    Taken by someone else
                  </button>
                  <button onClick={askClaude} style={{ ...ghostButtonStyle, marginLeft: "auto" }} disabled={aiLoading}>
                    {aiLoading ? (
                      <Loader2 size={14} style={{ marginRight: 6, animation: "spin 1s linear infinite" }} />
                    ) : (
                      <Sparkles size={14} style={{ marginRight: 6 }} />
                    )}
                    Ask Claude why
                  </button>
                </div>

                {aiNote && (
                  <div
                    style={{
                      marginTop: 14,
                      background: "rgba(0,0,0,0.2)",
                      borderLeft: `3px solid ${COLORS.blue}`,
                      padding: "10px 14px",
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: COLORS.chalk,
                      borderRadius: 4,
                    }}
                  >
                    {aiNote}
                  </div>
                )}

                {/* runners up */}
                {runnersUp.length > 0 && (
                  <div style={{ marginTop: 16, display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {runnersUp.map((p) => (
                      <div
                        key={p.player}
                        style={{
                          fontSize: 12,
                          background: "rgba(0,0,0,0.18)",
                          padding: "6px 10px",
                          borderRadius: 6,
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <PosBadge pos={p.position} small />
                        {p.player}
                        <span style={{ color: COLORS.chalkDim, fontFamily: "'IBM Plex Mono', monospace" }}>
                          {p.score.toFixed(1)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <Panel title="No players available">
                <div style={{ fontSize: 13, color: COLORS.chalkDim }}>
                  Upload projections or reset the draft to see recommendations.
                </div>
              </Panel>
            )}

            {/* Available players table */}
            <Panel title="Available players" icon={<TrendingUp size={14} />} noPad>
              <div style={{ display: "flex", gap: 8, padding: "0 16px 12px", flexWrap: "wrap" }}>
                <input
                  placeholder="Search player..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={searchInputStyle}
                />
                {["ALL", ...POSITIONS].map((pos) => (
                  <button
                    key={pos}
                    onClick={() => setPosFilter(pos)}
                    style={{
                      ...ghostButtonStyle,
                      padding: "4px 10px",
                      fontSize: 11,
                      background: posFilter === pos ? COLORS.gold : "transparent",
                      color: posFilter === pos ? COLORS.bg : COLORS.chalk,
                      borderColor: posFilter === pos ? COLORS.gold : COLORS.line,
                    }}
                  >
                    {pos}
                  </button>
                ))}
              </div>
              <div style={{ maxHeight: 420, overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ position: "sticky", top: 0, background: COLORS.panel, zIndex: 1 }}>
                      {["Player", "Pos", "Team", "Bye", "VBD", "Score", ""].map((h) => (
                        <th key={h} style={thStyle}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTable.slice(0, 60).map((p) => (
                      <tr key={p.player} style={{ borderBottom: `1px solid ${COLORS.line}` }}>
                        <td style={tdStyle}>{p.player}</td>
                        <td style={tdStyle}><PosBadge pos={p.position} small /></td>
                        <td style={{ ...tdStyle, color: COLORS.chalkDim }}>{p.team}</td>
                        <td style={{ ...tdStyle, color: p.byeConflicts > 0 ? COLORS.amber : COLORS.chalkDim, fontFamily: "'IBM Plex Mono', monospace" }}>
                          {p.bye_week ?? "—"}
                        </td>
                        <td style={{ ...tdStyle, fontFamily: "'IBM Plex Mono', monospace" }}>{p.vbd.toFixed(1)}</td>
                        <td style={{ ...tdStyle, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.gold, fontWeight: 600 }}>
                          {p.score.toFixed(1)}
                        </td>
                        <td style={tdStyle}>
                          <div style={{ display: "flex", gap: 4 }}>
                            <button onClick={() => draftPlayer(p, true)} title="Draft to my team" style={iconButtonStyle}>
                              <Check size={13} />
                            </button>
                            <button onClick={() => draftPlayer(p, false)} title="Taken by someone else" style={iconButtonStyle}>
                              <X size={13} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </div>
      </div>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        input[type="range"] { height: 4px; }
        table th, table td { text-align: left; }
      `}</style>
    </div>
  );
}

/* ---------------------------------------------------------------
   Small presentational components
----------------------------------------------------------------*/
function Panel({ title, icon, children, noPad }) {
  return (
    <div
      style={{
        background: COLORS.panel,
        border: `1px solid ${COLORS.line}`,
        borderRadius: 8,
        padding: noPad ? "16px 0 0" : 16,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontFamily: "'Oswald', sans-serif",
          fontSize: 13,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: COLORS.chalkDim,
          marginBottom: 12,
          padding: noPad ? "0 16px" : 0,
        }}
      >
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}

function PosBadge({ pos, small }) {
  const posColors = {
    QB: "#C1443C", RB: "#4E9A5B", WR: COLORS.blue, TE: COLORS.amber, K: "#8B7FB0", DST: "#7A8C7D",
  };
  return (
    <span
      style={{
        display: "inline-block",
        background: posColors[pos] || COLORS.chalkDim,
        color: "#fff",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: small ? 10 : 11,
        fontWeight: 600,
        padding: small ? "1px 5px" : "2px 7px",
        borderRadius: 4,
        letterSpacing: "0.02em",
      }}
    >
      {pos}
    </span>
  );
}

function ReasonTag({ label, tone }) {
  const toneColors = {
    gold: COLORS.gold, amber: COLORS.amber, blue: COLORS.blue, chalk: COLORS.chalk, chalkDim: COLORS.chalkDim,
  };
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 5, color: toneColors[tone] }}>
      {tone === "amber" && <AlertTriangle size={12} />}
      {label}
    </span>
  );
}

function RuleSlider({ label, hint, value, onChange }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
        <span>{label}</span>
        <span style={{ fontFamily: "'IBM Plex Mono', monospace", color: COLORS.chalkDim }}>{value.toFixed(1)}×</span>
      </div>
      <input
        type="range"
        min={0}
        max={2}
        step={0.1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: COLORS.gold, marginTop: 4 }}
      />
      <div style={{ fontSize: 10.5, color: COLORS.chalkDim, marginTop: 2 }}>{hint}</div>
    </div>
  );
}

function LabeledNumber({ label, value, onChange, min, max }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
      <span style={{ color: COLORS.chalkDim }}>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{
          width: 52,
          background: COLORS.panelLight,
          border: `1px solid ${COLORS.line}`,
          borderRadius: 4,
          color: COLORS.chalk,
          padding: "4px 6px",
          fontFamily: "'IBM Plex Mono', monospace",
        }}
      />
    </div>
  );
}

/* ---------------------------------------------------------------
   Shared inline styles
----------------------------------------------------------------*/
const ghostButtonStyle = {
  display: "inline-flex",
  alignItems: "center",
  background: "transparent",
  border: `1px solid ${COLORS.line}`,
  color: COLORS.chalk,
  borderRadius: 6,
  padding: "8px 14px",
  fontSize: 13,
  cursor: "pointer",
};

const primaryButtonStyle = {
  display: "inline-flex",
  alignItems: "center",
  background: COLORS.gold,
  border: "none",
  color: COLORS.bg,
  borderRadius: 6,
  padding: "8px 16px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const iconButtonStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 24,
  height: 24,
  background: COLORS.panelLight,
  border: `1px solid ${COLORS.line}`,
  color: COLORS.chalk,
  borderRadius: 4,
  cursor: "pointer",
};

const searchInputStyle = {
  flex: 1,
  minWidth: 160,
  background: COLORS.panelLight,
  border: `1px solid ${COLORS.line}`,
  borderRadius: 6,
  padding: "6px 10px",
  fontSize: 12,
  color: COLORS.chalk,
};

const thStyle = {
  fontSize: 10.5,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: COLORS.chalkDim,
  padding: "8px 12px",
  borderBottom: `1px solid ${COLORS.line}`,
};

const tdStyle = {
  padding: "8px 12px",
};
