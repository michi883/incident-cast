"""Tests for the steerable step-graph replay builder.

These guard the properties that make the workspace *a guided investigation*:
- the graph is well-formed (valid start, every choice resolves),
- whatever the user steers, the room always reaches convergence,
- convergence lands on the secret-access theory, backed by the rule-based aggregator,
- every revealed finding cites real, parameter-substituted SPL + rows.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

from incidentcast.aggregator import aggregate
from incidentcast.replay import _materialize_findings, build_replay, load_case
from incidentcast.specialists.access import ACCESS_SPEC
from incidentcast.specialists.blast_radius import BLAST_RADIUS_SPEC
from incidentcast.specialists.deployment import DEPLOYMENT_SPEC
from incidentcast.specialists.reliability import RELIABILITY_SPEC

CASE_PATH = Path("data/cases/cloud_run_secret_loss.yaml")

ALL_SPECS = {
    "reliability": RELIABILITY_SPEC,
    "deployment": DEPLOYMENT_SPEC,
    "blast_radius": BLAST_RADIUS_SPEC,
    "access": ACCESS_SPEC,
}


def _specs_for(case):
    return {name: ALL_SPECS[name] for name in case.specialists}


@pytest.fixture(scope="module")
def replay():
    case = load_case(CASE_PATH)
    return build_replay(case, _specs_for(case))


def _edges(step) -> list[str]:
    """Outgoing transitions: user choices plus the autonomous auto-advance target."""
    return [c.goto for c in step.choices] + ([step.next] if step.next else [])


def test_graph_is_well_formed(replay) -> None:
    ids = {s.id for s in replay.steps}
    assert replay.start in ids
    for s in replay.steps:
        for goto in _edges(s):
            assert goto in ids, f"step {s.id} -> unknown {goto}"
        # A step is either a decision (choices) or autonomous (next) — never both.
        assert not (s.choices and s.next), f"step {s.id} has both choices and next"


def test_decisions_only_punctuate_the_investigation(replay) -> None:
    # The whole point of this iteration: decisions are rare. The user guides ~3 times; the
    # rest of the steps advance on their own.
    decisions = [s for s in replay.steps if s.choices]
    auto = [s for s in replay.steps if s.next]
    assert len(decisions) == 3, f"expected 3 decisions, got {len(decisions)}"
    assert len(auto) >= len(decisions), "the room must run itself more than it asks"


def test_opening_step_has_no_consensus(replay) -> None:
    start = next(s for s in replay.steps if s.id == replay.start)
    assert not start.consensus.converged
    assert start.choices, "the opening step must offer the user a choice"


def test_every_step_reaches_convergence(replay) -> None:
    # From any reachable step, following the auto-advances and/or some choices lands on a
    # converged terminal — the room always converges no matter how the user steers.
    goto = {s.id: _edges(s) for s in replay.steps}
    converged_terminals = {
        s.id
        for s in replay.steps
        if not s.choices and s.next is None and s.consensus.converged
    }
    assert converged_terminals

    # Reverse-reachability from the converged terminals.
    can_reach = set(converged_terminals)
    changed = True
    while changed:
        changed = False
        for sid, nxts in goto.items():
            if sid not in can_reach and any(n in can_reach for n in nxts):
                can_reach.add(sid)
                changed = True

    # Every step reachable from start must be able to reach convergence.
    seen = set()
    q = deque([replay.start])
    while q:
        sid = q.popleft()
        if sid in seen:
            continue
        seen.add(sid)
        q.extend(goto[sid])
    assert seen <= can_reach, f"dead ends: {seen - can_reach}"


def test_converges_on_secret(replay) -> None:
    terminals = [
        s
        for s in replay.steps
        if not s.choices and s.next is None and s.consensus.converged
    ]
    assert terminals
    for t in terminals:
        assert t.consensus.leading_theory == "secret"
        confirmed = [th.id for th in t.theories if th.status == "confirmed"]
        assert confirmed == ["secret"]


def test_branches_then_funnels(replay) -> None:
    # Early divergence (the opening offers ≥2 distinct directions) and genuine rejoining:
    # branches funnel back together so the narrative stays controlled.
    start = next(s for s in replay.steps if s.id == replay.start)
    assert len({c.goto for c in start.choices}) >= 2

    incoming: dict[str, int] = {}
    for s in replay.steps:
        for goto in _edges(s):
            incoming[goto] = incoming.get(goto, 0) + 1
    merge_points = [sid for sid, n in incoming.items() if n >= 2]
    assert len(merge_points) >= 2, "expected branches to rejoin at merge points"


def test_a_witness_reacts_to_another(replay) -> None:
    # The pivotal step: Access posts the 583 audit denials and Reliability migrates to 'secret'
    # in the same step — the room reacting to itself.
    for step in replay.steps:
        by_spec = {w.specialist: w for w in step.witnesses}
        rel, acc = by_spec.get("reliability"), by_spec.get("access")
        if rel and acc and rel.supports == "secret" and acc.supports == "secret":
            break
    else:
        pytest.fail("expected a step where reliability migrates onto the secret theory")


def test_aggregator_guardrail_anchors_on_revision(replay) -> None:
    case = load_case(CASE_PATH)
    by_specialist, _ = _materialize_findings(case, _specs_for(case))
    clusters = aggregate(by_specialist)
    assert clusters
    assert clusters[0].entities.get("revision") == "checkout-api-00042"


def test_revealed_findings_cite_real_evidence(replay) -> None:
    sections = {s.spec.name: s.findings for s in replay.deck.specialists}
    seen = 0
    for step in replay.steps:
        for ref in step.revealed_findings:
            f = sections[ref.specialist][ref.finding_index]
            assert f.source_query_spl and "$" not in f.source_query_spl
            assert f.source_rows
            seen += 1
    assert seen > 0


def test_uses_operational_verbs_not_next_prev(replay) -> None:
    banned = {"next", "previous", "prev", "approve", "reject", "correct", "wrong"}
    for s in replay.steps:
        for c in s.choices:
            first = c.label.strip().lower().split()[0]
            assert first not in banned, f"non-operational choice label: {c.label!r}"


def test_unknown_goto_is_rejected() -> None:
    case = load_case(CASE_PATH)
    case.steps[0].choices[0].goto = "nowhere"
    with pytest.raises(ValueError, match="unknown step"):
        build_replay(case, _specs_for(case))


def test_dead_end_is_rejected() -> None:
    # Sever an autonomous step's onward transition so it can no longer reach convergence.
    case = load_case(CASE_PATH)
    survey = next(s for s in case.steps if s.id == "p1_scope")
    survey.next = None
    survey.choices = []
    survey.consensus.converged = False
    with pytest.raises(ValueError, match="cannot reach convergence"):
        build_replay(case, _specs_for(case))
