# IncidentCast — Architecture Diagram

IncidentCast is a **live incident reasoning room**: four specialist perspectives
(Reliability, Deployment, Access, Blast Radius) investigate one incident, theories rise
and fall as evidence lands, and the room converges on a single root cause. **Every piece of
evidence is a real Splunk search** — run through the official **Splunk MCP Server** or the
**Splunk SDK** — surfaced behind each claim as the literal SPL and the rows it returned.

## Data + control flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ SYNTHETIC INCIDENT DATA (authored once, ingested into Splunk)                             │
│                                                                                           │
│  data/scenarios/cloud_run_secret_loss/                                                    │
│    scenario.yaml  ── single source of truth (timeline, entities, error rates) ──┐         │
│    generate.py    ── emits HEC event payloads ──┐                               │         │
│    ingest.py      ── batches → HEC POST ────────┘                               │         │
└──────────────────────────────────────────────────┬────────────────────────────┼─────────┘
                                                    │ HTTPS HEC :8088             │
                                                    ▼                             │
                          ┌──────────────────────────────────────────┐           │
                          │  SPLUNK ENTERPRISE (local, 10.x)          │           │
                          │  indexes: app_logs, app_metrics, deploys, │           │
                          │           cloud_audit, iam_changes        │           │
                          └───────┬───────────────────────┬──────────┘           │
                 SPL via SDK :8089│                       │ SPL via MCP           │
                                  │                       │ (Streamable HTTP,     │
                                  │                       │  JSON-RPC over HTTPS) │
                                  │                       ▼                       │
                                  │     ┌──────────────────────────────────────┐ │
                                  │     │ Splunk MCP Server (Splunkbase 7931)  │ │
                                  │     │ :8089/services/mcp                   │ │
                                  │     │ tool: splunk_run_query               │ │
                                  │     └───────────────────┬──────────────────┘ │
                                  │                         │                     │
                                  ▼                         ▼                     │
            ┌───────────────────────────────────────────────────────────┐       │
            │  QueryInterface  (incidentcast/splunk/interface.py)         │       │
            │  one Protocol, three interchangeable backends:              │       │
            │    • FixtureQueryClient  → data/fixtures/*.json  (offline)  │       │
            │    • SplunkSDKQueryClient → splunklib jobs.oneshot          │       │
            │    • SplunkMCPQueryClient → MCP splunk_run_query            │       │
            └───────────────┬───────────────────────────┬─────────────────┘       │
                            │                           │                          │
        ┌───────────────────┘                           └──────────────────┐      │
        ▼  PATH A — cinematic replay (the product)                         ▼  PATH B — agentic
┌──────────────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ incidentcast cast <case>.yaml --backend …     │   │ incidentcast investigate <incident>    │
│                                                │   │   --backend mcp                        │
│ authored case YAML (theories, 3 decisions, ◄──┼───┘ 4 LLM specialists, each owning a       │
│   step graph, witness lines, which SPL each   │     non-overlapping SPL repertoire, call   │
│   finding cites) ── narrative scaffold        │     splunk_run_query autonomously and emit │
│                ↓                               │     evidence-cited Findings                │
│ replay.materialize_via_backend(): run each     │                ↓                          │
│   authored query LIVE through QueryInterface,  │     aggregator.aggregate() (rule-based     │
│   bind real rows + backend + job_id            │       clustering: time window + shared    │
│                ↓                               │       entity + shared tag → SharedEvidence)│
│ aggregator.aggregate() as a BUILD-TIME         │                ↓                          │
│   guardrail (top cluster must anchor on the    │     deck.build_deck()                     │
│   revision)                                    │                                            │
│                ↓                               │                                            │
│ build_replay() → InvestigationReplay + Deck    │                                            │
└───────────────┬────────────────────────────────┘   └───────────────┬────────────────────┘
                │ web/public/cases/<id>.json                          │ web/public/decks/<id>.json
                ▼                                                      ▼
        ┌─────────────────────────────────────────────────────────────────────────┐
        │  web/  — Next.js 14 / React (zod-validated artifacts)                     │
        │                                                                           │
        │   /cases/[id]  InvestigationWorkspace  ── the live reasoning room:        │
        │      TheoryStrip · InvestigationStage · ActivityFeed · ChoicePrompt       │
        │      auto-advancing beats; ~3 steer points; converges on screen           │
        │      SettingsMenu drawer + LiveSplunkEvidence modal → literal SPL +       │
        │      rows + "source: Splunk MCP/SDK" (live MCP query on demand)           │
        │                                                                           │
        │   /decks/[id]  DeckView forensic deep-dive (SharedTimeline +              │
        │      SharedEvidenceCard + SpecialistSection + EvidenceDrawer)             │
        └───────────────────────────────────────────────────────────────────────────┘
```

### PATH C — live MCP evidence at view time (runtime Splunk AI capability)

Beyond cast-time sourcing, the converged room can prove a finding *live* on demand. Opening a
proof's SPL in the compact **Live Splunk Evidence** modal issues a fresh MCP query while you watch:

```
IncidentCast UI ("Inspect evidence" → "Open ↗" on a proof row)
   → Evidence API   GET /api/splunk/evidence?caseId=…&name=…&backend=mcp
      → scripts/splunk_admin.py  mcp-query   (validates query ownership; logs the call)
         → SplunkMCPQueryClient.run()  →  Splunk MCP Server  splunk_run_query tool
            → Splunk Enterprise  →  returned rows
      ← {ok, backend:"mcp", tool_name, source:"Splunk MCP Server", spl, rowCount, rows, executedAt}
   → modal renders:  Splunk MCP connected · Live MCP query executed · N rows returned from Splunk
   ↳ on MCP unset/unreachable → falls back to captured replay rows, labeled "MCP unavailable"
```

This is the same `SplunkMCPQueryClient` the agents use — so a judge can trigger a real, auditable
Splunk-AI tool call straight from the UI, with fixture replay as a non-blocking safety net.

## Why two paths, one interface

- **Path A (cast → replay)** is the product: a deterministic, cinematic investigation. The
  *narrative* (which theories exist, the ~3 decision points, the convergence climax) is
  authored per case, but the *evidence* under every claim is fetched live from Splunk at cast
  time via `QueryInterface`. Each `Finding` records the `backend` (`fixture`/`sdk`/`mcp`) and
  `job_id` it came from, surfaced in the UI.
- **Path B (investigate)** is the autonomous proof: four LLM specialist agents call the Splunk
  MCP Server's `splunk_run_query` themselves and emit evidence-cited findings — this is the
  "real agents on Splunk" demonstration.
- Both paths share the **same `QueryInterface`**, the same **rule-based aggregator** (cross-agent
  agreement, never LLM self-confidence, is the convergence signal), and the same Splunk data.

## Offline vs. live

Judges run the public repo **offline**: `FixtureQueryClient` serves canned rows from
`data/fixtures/`, so `cast --backend fixture` reproduces the exact committed
`web/public/cases/<id>.json`. `scripts/refresh_fixtures.py` regenerates those fixtures from
live Splunk so **fixture == live == the committed artifact**. The `--backend mcp` / `--backend
sdk` runs (shown in the demo video) prove the same pipeline against a real Splunk instance.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for component-level detail and design principles.
