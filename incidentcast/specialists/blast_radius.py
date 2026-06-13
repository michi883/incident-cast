"""Blast Radius Investigator — answers 'who and what is affected?'

Distinct from Reliability: Reliability says *what is broken*; Blast Radius says
*who is affected by it*. Owned queries pivot the error/traffic data by tenant,
region, endpoint, and downstream service to expose the **shape** of the impact.
"""

from __future__ import annotations

from .base import QueryTemplate, SpecialistSpec

BLAST_RADIUS_QUERIES: list[QueryTemplate] = [
    QueryTemplate(
        name="blast_radius_error_share_by_tenant",
        purpose="Are all tenants affected equally, or is this concentrated in a subset?",
        spl=(
            'search index=app_logs sourcetype=access_log service=$service$ tenant=* '
            '| stats count as requests, count(eval(status>=500)) as errors by tenant '
            '| eval error_rate_pct=round(errors*100.0/requests, 2) '
            '| sort -error_rate_pct'
        ),
        owned_by="blast_radius",
        expected_columns=["tenant", "requests", "errors", "error_rate_pct"],
    ),
    QueryTemplate(
        name="blast_radius_error_share_by_endpoint",
        purpose="Which endpoints carry the failure? Healthy slices (e.g. /healthz) help bound the blast.",
        spl=(
            'search index=app_logs sourcetype=access_log service=$service$ '
            '| stats count as requests, count(eval(status>=500)) as errors by endpoint '
            '| eval error_rate_pct=round(errors*100.0/requests, 2) '
            '| sort -error_rate_pct'
        ),
        owned_by="blast_radius",
        expected_columns=["endpoint", "requests", "errors", "error_rate_pct"],
    ),
    QueryTemplate(
        name="blast_radius_downstream_impact",
        purpose="Are downstream services seeing knock-on errors? If so, the blast extends past the origin.",
        spl=(
            'search index=app_logs sourcetype=access_log upstream=$service$ '
            '| stats count as requests, count(eval(status>=500)) as errors by service '
            '| eval error_rate_pct=round(errors*100.0/requests, 2) '
            '| sort -errors'
        ),
        owned_by="blast_radius",
        expected_columns=["service", "requests", "errors", "error_rate_pct"],
    ),
    QueryTemplate(
        name="blast_radius_region_share",
        purpose="Is one region affected or all of them? Distinguishes regional outage from global failure.",
        spl=(
            'search index=app_logs sourcetype=access_log service=$service$ region=* '
            '| stats count as requests, count(eval(status>=500)) as errors by region '
            '| eval error_rate_pct=round(errors*100.0/requests, 2) '
            '| sort -error_rate_pct'
        ),
        owned_by="blast_radius",
        expected_columns=["region", "requests", "errors", "error_rate_pct"],
    ),
]


BLAST_RADIUS_SPEC = SpecialistSpec(
    name="blast_radius",
    title="Blast Radius Investigator",
    goal="Establish the scope of impact — who and what is affected by the failure.",
    lead_question="Who and what is affected?",
    sub_questions=[
        "Which tenants/customers are seeing the failure, and at what rate?",
        "Which endpoints carry the failure vs which remain healthy?",
        "Are downstream services seeing knock-on errors?",
        "Is the failure regional or global?",
    ],
    query_repertoire=BLAST_RADIUS_QUERIES,
    output_tags=[
        "impact:tenant",
        "impact:endpoint",
        "impact:region",
        "impact:downstream",
        "service:*",
        "tenant:*",
        "endpoint:*",
        "region:*",
        "downstream:*",
    ],
)
