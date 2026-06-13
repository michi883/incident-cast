"""Deployment Investigator — answers 'what changed?'

Owned query repertoire focused on **changes** in the incident window: revisions
deployed, commit messages, rollout state, CI build provenance. Does **not**
query for symptoms, IAM, or downstream impact — those belong to other
specialists.
"""

from __future__ import annotations

from .base import QueryTemplate, SpecialistSpec

DEPLOYMENT_QUERIES: list[QueryTemplate] = [
    QueryTemplate(
        name="deployment_recent_deploys",
        purpose="Deploys for the affected service in the recent history leading up to and into the incident window.",
        spl=(
            'search index=deploys sourcetype=cloud_run_deploy service=$service$ '
            '| eval deploy_time=strftime(_time, "%Y-%m-%dT%H:%M:%SZ") '
            '| table deploy_time, revision, commit_message, build_id, actor, rollout, rollback '
            '| sort -deploy_time'
        ),
        owned_by="deployment",
        expected_columns=[
            "deploy_time",
            "revision",
            "commit_message",
            "build_id",
            "actor",
            "rollout",
            "rollback",
        ],
    ),
    QueryTemplate(
        name="deployment_deploys_in_window",
        purpose="Deploys that landed inside the incident window. These are the suspect changes correlated to the symptoms.",
        spl=(
            'search index=deploys sourcetype=cloud_run_deploy service=$service$ '
            '| eval deploy_time=strftime(_time, "%Y-%m-%dT%H:%M:%SZ") '
            '| table deploy_time, revision, commit_message, build_id, actor '
            '| sort -deploy_time'
        ),
        owned_by="deployment",
        expected_columns=["deploy_time", "revision", "commit_message", "build_id", "actor"],
    ),
    QueryTemplate(
        name="deployment_revision_provenance",
        purpose="Full provenance of every revision seen recently — commit message, build id, actor — for change-attribution.",
        spl=(
            'search index=deploys sourcetype=cloud_run_deploy service=$service$ '
            '| stats values(commit_message) as commit_message, values(build_id) as build_id, '
            'values(actor) as actor, min(_time) as deployed_at_epoch, max(rollout) as rollout '
            'by revision '
            '| eval deployed_at=strftime(deployed_at_epoch, "%Y-%m-%dT%H:%M:%SZ") '
            '| table revision, deployed_at, commit_message, build_id, actor, rollout '
            '| sort -deployed_at'
        ),
        owned_by="deployment",
        expected_columns=["revision", "deployed_at", "commit_message", "build_id", "actor", "rollout"],
    ),
    QueryTemplate(
        name="deployment_rollback_check",
        purpose="Were any rollbacks issued for this service in the recent past? A clean record means change went forward only.",
        spl=(
            'search index=deploys sourcetype=cloud_run_deploy service=$service$ '
            '| eval deploy_time=strftime(_time, "%Y-%m-%dT%H:%M:%SZ") '
            '| stats count as deploy_count, count(eval(rollback=true)) as rollback_count, '
            'values(eval(if(rollback=true, revision, null()))) as rolled_back_revisions '
        ),
        owned_by="deployment",
        expected_columns=["deploy_count", "rollback_count", "rolled_back_revisions"],
    ),
]


DEPLOYMENT_SPEC = SpecialistSpec(
    name="deployment",
    title="Deployment Investigator",
    goal="Identify what changed in the affected service shortly before the incident.",
    lead_question="What changed?",
    sub_questions=[
        "What deploys landed in or shortly before the incident window?",
        "Which specific revision is most recent and what did it touch (commit message, build id, actor)?",
        "Is there a sequence of related deploys, or just one suspect change?",
        "Were any rollbacks issued? If not, the most recent deploy is the live one.",
    ],
    query_repertoire=DEPLOYMENT_QUERIES,
    output_tags=[
        "change:deploy",
        "change:rollout",
        "change:rollback",
        "revision:*",
        "service:*",
        "build_id:*",
        "actor:*",
    ],
)
