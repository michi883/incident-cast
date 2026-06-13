"""Reliability Investigator — answers 'what is broken and how badly?'

Owned query repertoire focused on symptoms: error rate over time, latency
percentiles, status code distribution, error type breakdown. Does **not**
query for changes, IAM, or downstream blast — those belong to other
specialists. Repertoire ownership is enforced by
``tests/test_repertoire_ownership.py``.
"""

from __future__ import annotations

from .base import QueryTemplate, SpecialistSpec

RELIABILITY_QUERIES: list[QueryTemplate] = [
    QueryTemplate(
        name="reliability_error_rate_over_time",
        purpose="Per-minute error rate (status>=500 share of requests) for the affected service.",
        spl=(
            'search index=app_logs sourcetype=access_log service=$service$ '
            '| bin _time span=1m '
            '| stats count as requests, count(eval(status>=500)) as errors by _time '
            '| eval error_rate_pct=round(errors*100.0/requests, 2)'
        ),
        owned_by="reliability",
        expected_columns=["_time", "requests", "errors", "error_rate_pct"],
    ),
    QueryTemplate(
        name="reliability_latency_percentiles",
        purpose="Per-minute p50/p95/p99 latency for the affected service.",
        spl=(
            'search index=app_logs sourcetype=access_log service=$service$ '
            '| bin _time span=1m '
            '| stats perc50(latency_ms) as p50_ms, perc95(latency_ms) as p95_ms, '
            'perc99(latency_ms) as p99_ms by _time'
        ),
        owned_by="reliability",
        expected_columns=["_time", "p50_ms", "p95_ms", "p99_ms"],
    ),
    QueryTemplate(
        name="reliability_status_code_distribution",
        purpose="Distribution of HTTP status codes during the incident window.",
        spl=(
            'search index=app_logs sourcetype=access_log service=$service$ '
            '| stats count by status '
            '| rename status as status_code '
            '| eventstats sum(count) as total '
            '| eval share_pct=round(count*100.0/total, 2) '
            '| fields status_code, count, share_pct'
        ),
        owned_by="reliability",
        expected_columns=["status_code", "count", "share_pct"],
    ),
    QueryTemplate(
        name="reliability_error_type_breakdown",
        purpose="Top error types/messages seen during the incident window.",
        spl=(
            'search index=app_logs sourcetype=app_log service=$service$ level=ERROR '
            '| stats count, min(_time) as first_seen_epoch, max(_time) as last_seen_epoch '
            'by error_type, message '
            '| eval first_seen=strftime(first_seen_epoch, "%Y-%m-%dT%H:%M:%SZ") '
            '| eval last_seen=strftime(last_seen_epoch, "%Y-%m-%dT%H:%M:%SZ") '
            '| fields error_type, message, count, first_seen, last_seen '
            '| sort -count'
        ),
        owned_by="reliability",
        expected_columns=["error_type", "message", "count", "first_seen", "last_seen"],
    ),
]


RELIABILITY_SPEC = SpecialistSpec(
    name="reliability",
    title="Reliability Investigator",
    goal="Characterize what is broken in the affected service and how badly.",
    lead_question="What is broken and how badly?",
    sub_questions=[
        "When did the degradation start and how steep was the change?",
        "Which signals confirm degradation: error rate, latency, status codes, error types?",
        "Is the degradation sustained or recovering?",
        "What error message or class dominates after the change?",
    ],
    query_repertoire=RELIABILITY_QUERIES,
    output_tags=[
        "symptom:error_rate_spike",
        "symptom:latency_degradation",
        "symptom:5xx_spike",
        "error_type:*",
        "service:*",
    ],
)
