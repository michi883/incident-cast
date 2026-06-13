"""Specialist runtime.

A ``Specialist`` runs one specialist's investigation loop. Two modes:

- **Gateway mode** (``backend=fixture`` or ``backend=sdk``): the specialist
  calls our in-process ``mcp__icast__run_query`` tool, which forwards the
  parameterized SPL through the supplied ``QueryInterface``. Used for offline
  fixture demos (M1) and direct Splunk SDK queries (M2).

- **MCP-direct mode** (``backend=mcp``): the specialist calls Splunk's own
  ``mcp__splunk__splunk_run_query`` tool *directly*. We attach the Splunk MCP
  server as an HTTP MCP server over SSE, fetch its tools, and observe tool execution
  payloads so we can still cite the exact SPL + rows in the deck.

In both modes the specialist also has an in-process ``mcp__icast__emit_finding``
tool that records structured ``Finding`` objects with mandatory source citation.
The system prompt is generated from the ``SpecialistSpec`` so the spec stays
the source of truth.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from google import genai
from google.genai import types

from ..splunk.interface import QueryInterface
from .base import Finding, IncidentContext, SpecialistSpec

# Cap how many rows we feed back to the model from a single query — keeps the
# context window healthy on chatty queries. The full row set is still kept in
# the QueryResult for citation in the deck.
MAX_ROWS_TO_MODEL = 50

# Splunk MCP tool that the agent calls in MCP-direct mode.
SPLUNK_MCP_RUN_QUERY = "mcp__splunk__splunk_run_query"


def _substitute(spl: str, params: dict[str, Any], incident: IncidentContext) -> str:
    """Replace ``$name$`` placeholders in an SPL template.

    Pulls values from ``params`` first, falling back to ``incident.hints``,
    then to literal incident fields (``earliest``, ``latest``).
    """
    sources = {
        **incident.hints,
        "earliest": incident.earliest,
        "latest": incident.latest,
        **params,
    }
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in sources:
            return m.group(0)
        return str(sources[key])
    return re.sub(r"\$([a-zA-Z_][a-zA-Z0-9_]*)\$", repl, spl)


def _normalize_spl(spl: str) -> str:
    """Whitespace-collapsed, lowercase form for SPL matching."""
    return " ".join(spl.strip().lower().split())


def _build_system_prompt(spec: SpecialistSpec, *, mode: str) -> str:
    """Render a specialist's spec into a self-contained system prompt.

    ``mode`` selects the tool surface:
    - ``"gateway"``: agent uses ``mcp__icast__run_query`` to call our backend.
    - ``"mcp"``: agent uses ``mcp__splunk__splunk_run_query`` directly.
    """
    repertoire_lines = []
    for tpl in spec.query_repertoire:
        repertoire_lines.append(
            f"  - **{tpl.name}**\n"
            f"      purpose: {tpl.purpose}\n"
            f"      spl: {tpl.spl}"
        )
    repertoire = "\n".join(repertoire_lines)

    if mode == "mcp":
        how_to_query = f"""## How to run a query
You call **{SPLUNK_MCP_RUN_QUERY}** directly with these args:
  - ``query``: the parameterized SPL from your repertoire. Substitute ``$service$`` etc. using the incident hints.
  - ``earliest_time`` / ``latest_time``: from the incident.
  - ``row_limit``: 200 is fine; the MCP server returns JSON rows.

You may only run SPL drawn from your repertoire above. Do not invent or modify the structure of the query — only substitute ``$param$`` placeholders with concrete values."""
    else:
        how_to_query = """## How to run a query
You call **mcp__icast__run_query** with:
  - ``query_name``: the canonical name from your repertoire above (e.g. ``reliability_error_rate_over_time``).
  - ``params``: values for any ``$param$`` placeholders (the incident's ``earliest``, ``latest``, and ``hints`` like ``service`` are already injected automatically).

The tool returns up to {max_rows} rows from the backend.""".format(max_rows=MAX_ROWS_TO_MODEL)

    return f"""You are the **{spec.title}**, one of four parallel specialists investigating an incident in an AI incident room. You answer one question only:

  {spec.lead_question}

## Your goal
{spec.goal}

## Sub-questions to pursue (in order)
{chr(10).join(f'  {i+1}. {q}' for i, q in enumerate(spec.sub_questions))}

## Your owned query repertoire
You may only run SPL drawn from these templates. They are owned by you exclusively — no other specialist runs them.

{repertoire}

{how_to_query}

## How to emit a finding
After each query, decide whether the rows support a specific observation. If so, call **mcp__icast__emit_finding** with:
  - ``claim``: a concise, evidence-grounded sentence (≤240 chars).
  - ``severity``: one of "info", "notable", "critical".
  - ``timestamp``: ISO 8601 UTC, the event time the claim refers to.
  - ``entities``: identifying entities, e.g. {{"service": "checkout-api", "error_type": "PermissionDenied"}}.
  - ``source_query_spl``: the **exact SPL** you ran for this finding (copy-paste from your prior tool call).
  - ``source_rows``: 1–10 row dicts from that query's results.
  - ``tags``: cluster tags drawn from this specialist's namespaces: {", ".join(spec.output_tags)}. Substitute concrete values for ``*``. Example: ``error_type:PermissionDenied``.

Emit one finding per distinct observation. Do not bundle multiple observations into one finding.

## Hard rules
- Every claim must cite specific rows from your own queries. No claim without evidence.
- You may not emit a finding before running at least one query and reading the result.
- Do not invent values — only use values that appear in returned rows.
- Stay in your lane. Reliability characterizes symptoms. Deployment finds changes. Access finds permission events. Blast Radius finds scope. Other specialists are investigating in parallel and an aggregator will combine findings.
- Never suggest remediation actions. That is the human's decision, not yours.
- When you have answered your sub-questions, stop. Reply with one short sentence summarizing what you found. Do not call any more tools.
"""


def _build_user_prompt(spec: SpecialistSpec, incident: IncidentContext) -> str:
    return f"""Incident in flight.

- id: {incident.id}
- title: {incident.title}
- triggered at: {incident.triggered_at.isoformat()}
- investigation window: earliest={incident.earliest}, latest={incident.latest}
- hints: {json.dumps(incident.hints)}

Investigate as the **{spec.title}**. Pursue your sub-questions in order, run the queries you need, and emit findings as you reach evidence-supported conclusions. Stop when your sub-questions are answered."""


def _match_template(spec: SpecialistSpec, spl: str, incident: IncidentContext) -> str | None:
    """Return the canonical template name whose parameterized SPL matches ``spl``.

    Normalizes whitespace+case. Substitutes the parameterized templates using
    a generous wildcard for ``$param$`` so concrete values like ``service=checkout-api``
    still match. Returns ``None`` if no template matches.
    """
    n = _normalize_spl(spl)
    for tpl in spec.query_repertoire:
        # Build a regex from the template by escaping then replacing $name$ → .+
        pat = re.escape(_normalize_spl(tpl.spl))
        pat = re.sub(r"\\\$[a-zA-Z_][a-zA-Z0-9_]*\\\$", r".+", pat)
        if re.fullmatch(pat, n):
            return tpl.name
    return None


class Specialist:
    """Runs one specialist's investigation loop.

    For ``fixture``/``sdk`` backends, pass a ``QueryInterface``. For ``mcp``,
    pass ``mcp_url`` and ``mcp_token``.
    """

    def __init__(
        self,
        spec: SpecialistSpec,
        backend: QueryInterface | None = None,
        *,
        mcp_url: str | None = None,
        mcp_token: str | None = None,
        model: str = "gemini-3.1-pro-preview",
        max_turns: int = 30,
        debug: bool = False,
    ):
        self.spec = spec
        self.backend = backend
        self.mcp_url = mcp_url
        self.mcp_token = mcp_token
        self.model = model
        self.max_turns = max_turns
        self.debug = debug
        if backend is None and not (mcp_url and mcp_token):
            raise ValueError(
                "Specialist requires either a QueryInterface backend OR mcp_url/mcp_token."
            )

    @property
    def mode(self) -> str:
        return "mcp" if self.mcp_url else "gateway"

    async def investigate(self, incident: IncidentContext) -> list[Finding]:
        if self.mode == "mcp":
            return await self._investigate_mcp(incident)
        return await self._investigate_gateway(incident)

    # ------------------------------------------------------------------ gateway

    async def _investigate_gateway(self, incident: IncidentContext) -> list[Finding]:
        findings: list[Finding] = []
        executed: dict[str, dict[str, Any]] = {}  # name → {spl, rows}
        templates_by_name = {t.name: t for t in self.spec.query_repertoire}
        assert self.backend is not None

        async def mcp__icast__run_query(query_name: str, params: dict = None) -> str:
            """Run a named SPL query from your owned repertoire and return a JSON string of results.

            Args:
                query_name: One of canonical templates in your repertoire.
                params: Values for $param$ placeholders in the template.
            """
            tpl = templates_by_name.get(query_name)
            if tpl is None:
                return json.dumps({
                    "error": f"'{query_name}' is not in this specialist's repertoire. Available: {list(templates_by_name.keys())}"
                })
            params_dict = params or {}
            spl = _substitute(tpl.spl, params_dict, incident)
            try:
                result = await self.backend.run(
                    query_name=query_name,
                    spl=spl,
                    earliest=incident.earliest,
                    latest=incident.latest,
                    params=params_dict,
                )
            except Exception as exc:
                return json.dumps({"error": f"backend.run failed: {exc}"})
            executed[query_name] = {"spl": spl, "rows": result.rows}
            payload = {
                "query_name": query_name,
                "spl": spl,
                "row_count": len(result.rows),
                "rows": result.rows[:MAX_ROWS_TO_MODEL],
                "truncated": len(result.rows) > MAX_ROWS_TO_MODEL,
            }
            return json.dumps(payload, default=str)

        async def mcp__icast__emit_finding(
            claim: str,
            timestamp: str,
            source_query_spl: str,
            source_rows: list[dict],
            severity: str = "notable",
            entities: dict = None,
            tags: list[str] = None,
        ) -> str:
            """Emit a single evidence-cited finding. Every claim MUST cite SPL + rows from a prior query.

            Args:
                claim: A concise, evidence-grounded sentence (<= 240 chars).
                timestamp: ISO 8601 UTC, the event time the claim refers to.
                source_query_spl: The EXACT SPL you ran for this finding (must match a prior query).
                source_rows: The specific row(s) cited (1-10 rows).
                severity: One of "info", "notable", "critical" (default: "notable").
                entities: Identifying entities, e.g. {"service": "checkout-api"}.
                tags: Cluster tags like "error_type:PermissionDenied".
            """
            spl = source_query_spl
            name = next((n for n, rec in executed.items() if rec["spl"] == spl), None)
            if not name:
                return json.dumps({
                    "error": "source_query_spl does not match any query you ran in this session, or that query is not in your repertoire. Re-run the query first, then cite its exact SPL."
                })
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                return json.dumps({"error": f"invalid timestamp: {exc}"})
            try:
                finding = Finding(
                    specialist=self.spec.name,
                    timestamp=ts,
                    claim=claim,
                    severity=severity,  # type: ignore
                    entities=entities or {},
                    source_query_name=name,
                    source_query_spl=spl,
                    source_rows=source_rows,
                    tags=tags or [],
                )
            except Exception as exc:
                return json.dumps({"error": f"invalid finding: {exc}"})
            findings.append(finding)
            return f"Recorded finding #{len(findings)}: {finding.claim}"

        client = genai.Client()
        config = types.GenerateContentConfig(
            system_instruction=_build_system_prompt(self.spec, mode="gateway"),
            tools=[mcp__icast__run_query, mcp__icast__emit_finding],
            temperature=0.0,
        )

        chat = client.aio.chats.create(model=self.model, config=config)
        user_prompt = _build_user_prompt(self.spec, incident)

        response = await chat.send_message(user_prompt)
        if self.debug and response.text:
            print(f"[{self.spec.name}] {response.text}")

        turn = 0
        while turn < self.max_turns:
            if not response.function_calls:
                break

            tool_responses = []
            for call in response.function_calls:
                func_name = call.name
                func_args = call.args

                if func_name == "mcp__icast__run_query":
                    result = await mcp__icast__run_query(**func_args)
                elif func_name == "mcp__icast__emit_finding":
                    result = await mcp__icast__emit_finding(**func_args)
                else:
                    result = json.dumps({"error": f"Unknown tool: {func_name}"})

                tool_responses.append(
                    types.Part.from_function_response(
                        name=func_name,
                        response={"result": result}
                    )
                )

            response = await chat.send_message(tool_responses)
            if self.debug and response.text:
                print(f"[{self.spec.name}] {response.text}")
            turn += 1

        return findings

    # --------------------------------------------------------------------- mcp

    async def _investigate_mcp(self, incident: IncidentContext) -> list[Finding]:
        findings: list[Finding] = []
        executed: dict[str, dict[str, Any]] = {}  # normalized_spl → {spl, name, rows}

        from mcp import ClientSession
        from mcp.client.sse import sse_client

        headers = {"Authorization": f"Bearer {self.mcp_token}"}
        async with sse_client(url=self.mcp_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                async def mcp__splunk__splunk_run_query(
                    query: str,
                    earliest_time: str = None,
                    latest_time: str = None,
                    row_limit: int = 200,
                ) -> str:
                    """Run a query directly on Splunk MCP server.

                    Args:
                        query: The literal SPL query to execute.
                        earliest_time: ISO-8601 earliest time.
                        latest_time: ISO-8601 latest time.
                        row_limit: Maximum number of rows to return (default is 200).
                    """
                    try:
                        tool_result = await session.call_tool(
                            "splunk_run_query",
                            arguments={
                                "query": query,
                                "earliest_time": earliest_time,
                                "latest_time": latest_time,
                                "row_limit": row_limit
                            }
                        )
                        rows: list[dict[str, Any]] = []
                        for block in tool_result.content:
                            if block.type == "text":
                                try:
                                    payload = json.loads(block.text)
                                except json.JSONDecodeError:
                                    continue
                                if isinstance(payload, dict) and "results" in payload:
                                    rows.extend(payload["results"])
                        
                        matched = _match_template(self.spec, query, incident)
                        executed[_normalize_spl(query)] = {
                            "spl": query,
                            "name": matched or "ad_hoc",
                            "rows": rows,
                        }
                        if self.debug:
                            print(
                                f"[{self.spec.name}] captured splunk_run_query → "
                                f"{matched or 'UNMATCHED'} ({len(rows)} rows)"
                            )
                        return "".join(b.text for b in tool_result.content if b.type == "text")
                    except Exception as exc:
                        return json.dumps({"error": f"Failed to run splunk query: {exc}"})

                async def mcp__icast__emit_finding(
                    claim: str,
                    timestamp: str,
                    source_query_spl: str,
                    source_rows: list[dict],
                    severity: str = "notable",
                    entities: dict = None,
                    tags: list[str] = None,
                ) -> str:
                    """Emit a single evidence-cited finding. Every claim MUST cite SPL + rows from a prior query.

                    Args:
                        claim: A concise, evidence-grounded sentence (<= 240 chars).
                        timestamp: ISO 8601 UTC, the event time the claim refers to.
                        source_query_spl: The EXACT SPL you ran for this finding (must match a prior query).
                        source_rows: The specific row(s) cited (1-10 rows).
                        severity: One of "info", "notable", "critical" (default: "notable").
                        entities: Identifying entities, e.g. {"service": "checkout-api"}.
                        tags: Cluster tags like "error_type:PermissionDenied".
                    """
                    spl = source_query_spl
                    rec = executed.get(_normalize_spl(spl))
                    name = rec["name"] if rec else None
                    if not name:
                        return json.dumps({
                            "error": "source_query_spl does not match any query you ran in this session, or that query is not in your repertoire. Re-run the query first, then cite its exact SPL."
                        })
                    try:
                        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    except ValueError as exc:
                        return json.dumps({"error": f"invalid timestamp: {exc}"})
                    try:
                        finding = Finding(
                            specialist=self.spec.name,
                            timestamp=ts,
                            claim=claim,
                            severity=severity,  # type: ignore
                            entities=entities or {},
                            source_query_name=name,
                            source_query_spl=spl,
                            source_rows=source_rows,
                            tags=tags or [],
                        )
                    except Exception as exc:
                        return json.dumps({"error": f"invalid finding: {exc}"})
                    findings.append(finding)
                    return f"Recorded finding #{len(findings)}: {finding.claim}"

                client = genai.Client()
                config = types.GenerateContentConfig(
                    system_instruction=_build_system_prompt(self.spec, mode="mcp"),
                    tools=[mcp__splunk__splunk_run_query, mcp__icast__emit_finding],
                    temperature=0.0,
                )

                chat = client.aio.chats.create(model=self.model, config=config)
                user_prompt = _build_user_prompt(self.spec, incident)

                response = await chat.send_message(user_prompt)
                if self.debug and response.text:
                    print(f"[{self.spec.name}] {response.text}")

                turn = 0
                while turn < self.max_turns:
                    if not response.function_calls:
                        break

                    tool_responses = []
                    for call in response.function_calls:
                        func_name = call.name
                        func_args = call.args

                        if func_name == "mcp__splunk__splunk_run_query":
                            result = await mcp__splunk__splunk_run_query(**func_args)
                        elif func_name == "mcp__icast__emit_finding":
                            result = await mcp__icast__emit_finding(**func_args)
                        else:
                            result = json.dumps({"error": f"Unknown tool: {func_name}"})

                        tool_responses.append(
                            types.Part.from_function_response(
                                name=func_name,
                                response={"result": result}
                            )
                        )

                    response = await chat.send_message(tool_responses)
                    if self.debug and response.text:
                        print(f"[{self.spec.name}] {response.text}")
                    turn += 1

        return findings
