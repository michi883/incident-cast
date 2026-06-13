# Architecture

IncidentCast is a live incident reasoning room. Four specialist perspectives
investigate one incident from different angles; theories rise and fall as evidence
lands and the room converges on a single, citation-grounded root cause.

There are two consumers of the same Splunk evidence, behind one `QueryInterface`:

- **`cast` → InvestigationReplay → `/cases/[id]`** — the cinematic product. An authored case
  (theories, ~3 decisions, step graph) supplies the narrative scaffold; the *evidence* under
  every claim is fetched **live from Splunk at cast time** via `QueryInterface`. This is the
  primary surface.
- **`investigate` → deck → `/decks/[id]`** — four LLM specialist agents that call the Splunk
  MCP Server's `splunk_run_query` autonomously and emit evidence-cited findings (the "real
  agents on Splunk" demonstration, and the forensic deep-dive view).

For the end-to-end data + control flow across both paths, see
[architecture_diagram.md](./architecture_diagram.md). The system diagram below details the
**agentic `investigate` path** and the shared aggregator/deck components.

## System diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  data/scenarios/cloud_run_secret_loss/                                       │
│    generate.py  →  ingest.py (HEC POST)  →  Splunk Enterprise               │
│                                              indexes:                        │
│                                                app_logs, app_metrics,        │
│                                                deploys, cloud_audit,         │
│                                                iam_changes                   │
└─────────────────────────────────────┬────────────────────────────────────────┘
                                      │
                                      ▼
                ┌─────────────────────────────────────────────┐
                │  Splunk MCP Server  (Splunkbase app 7931)   │
                │  HTTPS  https://<host>:8089/services/mcp    │
                │  tools: splunk_run_query, splunk_get_info,  │
                │         splunk_get_indexes, …               │
                └────────────────────┬────────────────────────┘
                                     │ MCP (JSON-RPC over HTTP)
                                     │
   ┌─────────────────────────────────┼─────────────────────────────────┐
   │  incidentcast.specialists.runtime.Specialist                      │
   │                                                                   │
   │  ┌───────────────────┐  ┌───────────────────┐                     │
   │  │ Reliability       │  │ Deployment        │   (parallel via     │
   │  │ symptoms          │  │ revisions/CI      │    asyncio.gather)  │
   │  └────────┬──────────┘  └────────┬──────────┘                     │
   │  ┌───────────────────┐  ┌───────────────────┐                     │
   │  │ Blast Radius      │  │ Access            │                     │
   │  │ tenant / endpoint │  │ IAM / audit       │                     │
   │  │ region / dwnstrm  │  │ permission events │                     │
   │  └────────┬──────────┘  └────────┬──────────┘                     │
   │                                                                   │
   │  Each specialist:                                                 │
   │   • generates its system prompt from its SpecialistSpec           │
   │     (goal, lead question, sub-questions, owned query repertoire)  │
   │   • calls mcp__splunk__splunk_run_query directly on Splunk MCP    │
   │   • emits structured Findings via mcp__icast__emit_finding        │
   │     (every claim cites the SPL + the rows it ran)                 │
   │                                                                   │
   │  Repertoire ownership is enforced by                              │
   │  tests/test_repertoire_ownership.py — no two specialists may      │
   │  own or import the same QueryTemplate.                            │
   └────────────────────────────────┬──────────────────────────────────┘
                                    │ list[Finding] per specialist
                                    ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  incidentcast.aggregator                                          │
   │                                                                   │
   │  Rule-based clustering (no LLM-judged convergence):               │
   │    • findings within ±5 min are eligible to share a cluster      │
   │    • cluster joins on any shared (key,value) entity              │
   │    • cluster joins on any shared tag                             │
   │    • support_count = distinct specialists in cluster             │
   │                                                                   │
   │  → list[SharedEvidence], sorted by # specialists desc             │
   └────────────────────────────────┬──────────────────────────────────┘
                                    ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  incidentcast.deck.build_deck                                     │
   │  → deck.json on disk (web/public/decks/<id>.json)                 │
   │                                                                   │
   │  Schema mirrored in web/lib/deck.ts (zod-validated on load).      │
   └────────────────────────────────┬──────────────────────────────────┘
                                    ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  web/ — Next.js 14 / React  ·  /decks/[id]  (DeckView)            │
   │  (the forensic deep-dive; the primary /cases/[id] room is the     │
   │   InvestigationWorkspace — see architecture_diagram.md PATH A)    │
   │                                                                   │
   │   DeckHeader        — incident metadata + counts                  │
   │   SharedTimeline    — bands per specialist, dots per finding,     │
   │                       vertical highlights where the bands align  │
   │   SharedEvidenceCard— narrative card per cluster, sorted by       │
   │                       strength of agreement                       │
   │   SpecialistSection — per-specialist findings list                │
   │   EvidenceChip      — clickable citation                          │
   │   EvidenceDrawer    — shows the literal SPL + raw rows            │
   │   ReviewPrompts     — "Review …" suggestions (never imperatives)  │
   └──────────────────────────────────────────────────────────────────┘
```

## Design principles

These are the non-negotiable principles the project is built around:

1. **Evidence over assertion.** Every claim in the deck cites a specific
   `(source_query_spl, source_rows)` pair. The `emit_finding` tool rejects
   citations that don't match a prior `splunk_run_query` the same specialist
   ran in this session.

2. **Splunk MCP is the agent surface, not a wrapper.** In `--backend mcp` mode
   the specialist agent literally calls `mcp__splunk__splunk_run_query` on the
   official Splunk MCP Server. A `PostToolUse` hook observes the call so we can
   bind the SPL back to the canonical owned `QueryTemplate` for the deck.

3. **Cross-agent agreement is the confidence signal.** The aggregator is
   rule-based, not LLM-judged. It clusters findings by structural overlap
   (time window, shared entities, shared tags). LLM "confidence" is never
   used as a confidence metric.

4. **The human decides.** Review prompts are framed as review prompts
   ("Review …", "Check …"), never as imperative remediation actions. The
   deck ends with "what to review next," not "what to do."

5. **Depth over breadth.** A `QueryInterface` Protocol decouples the
   specialists from the backend. Three backends (`fixture`, `sdk`, `mcp`)
   implement the same interface, so we can demo end-to-end without Splunk
   running and add MCP without touching specialist code.

## Specialist distinctness, enforced

Each specialist is constructed from a declarative `SpecialistSpec`:

- `goal` — one-sentence north star
- `lead_question` — the single question this specialist answers
- `sub_questions` — 3–5 concrete questions it pursues in order
- `query_repertoire` — the SPL templates it owns (and only those)
- `output_tags` — the tag namespaces it emits

The system prompt is generated from the spec, so the spec stays the source of
truth for what the specialist does. `tests/test_repertoire_ownership.py`
fails the build if any `QueryTemplate` is claimed by more than one specialist
or if a template's name doesn't carry its owner's prefix.

## Data flow on the demo scenario

The bundled scenario (`data/scenarios/cloud_run_secret_loss/`) simulates a
Cloud Run revision losing access to Secret Manager:

| Time (UTC) | Event                                                          | Index           |
|-----------:|----------------------------------------------------------------|-----------------|
| 14:01:12   | IAM binding removed: `secretmanager.secretAccessor` ✕ `checkout-api@…` | iam_changes, cloud_audit |
| 14:01:15   | Deploy `checkout-api-00042` ("migrate service account to least-privilege SA") | deploys |
| 14:02:03   | First `PERMISSION_DENIED` on `AccessSecretVersion`             | cloud_audit     |
| 14:02–14:14 | Error rate ~0.5% → ~30%, p99 latency ~185 ms → ~1.5 s         | app_logs        |
| 14:02–14:14 | Downstream order-fulfillment / notification / payment-gateway at ~100% error rate | app_logs |

All four specialists end up surfacing evidence pinned to the same set of
entities (revision `checkout-api-00042`, principal `checkout-api@acme-prod…`, secret
`checkout-stripe-key`, role `secretmanager.secretAccessor`). The aggregator
clusters them into a single `SharedEvidence` with `supporting_specialists = 4`,
which anchors convergence on:

> *All four specialists — reliability, deployment, access, blast radius —
> converged on revision `checkout-api-00042` in the same window.*

> Failure is confined to `us-central1` (~27%) with `us-east1`/`eu-west1` under 0.5%, and the
> checkout **write** path fails (~21%) while reads stay healthy — which is how Blast Radius
> rules out a regional outage and ties the fault to the secret, not the region.
