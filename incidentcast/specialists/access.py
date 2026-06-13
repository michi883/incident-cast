"""Access / Security Investigator — answers 'who can do what, and did that change?'

Owned queries focus on **permission events** in the incident window: IAM
binding changes, audit-log denials by principal, policy change provenance.
May legitimately have nothing to report on incidents unrelated to access —
that is fine and expected, and the spec says so explicitly in the prompt.
"""

from __future__ import annotations

from .base import QueryTemplate, SpecialistSpec

ACCESS_QUERIES: list[QueryTemplate] = [
    QueryTemplate(
        name="access_iam_changes_in_window",
        purpose="IAM binding changes (roles added/removed) recorded in the incident window.",
        spl=(
            'search index=iam_changes sourcetype=iam_binding_change '
            '| eval change_time=strftime(_time, "%Y-%m-%dT%H:%M:%SZ") '
            '| table change_time, action, role, member, resource, actor, change_reason '
            '| sort -change_time'
        ),
        owned_by="access",
        expected_columns=[
            "change_time", "action", "role", "member", "resource", "actor", "change_reason"
        ],
    ),
    QueryTemplate(
        name="access_audit_denials_by_principal",
        purpose="Audit-log permission-denied events grouped by the principal that was denied, in the incident window.",
        spl=(
            'search index=cloud_audit sourcetype=cloud_audit status=PERMISSION_DENIED '
            '| stats count as denials, values(method) as methods, values(resource) as resources, '
            'min(_time) as first_seen_epoch, max(_time) as last_seen_epoch by principal_email '
            '| eval first_denied=strftime(first_seen_epoch, "%Y-%m-%dT%H:%M:%SZ") '
            '| eval last_denied=strftime(last_seen_epoch, "%Y-%m-%dT%H:%M:%SZ") '
            '| table principal_email, denials, methods, resources, first_denied, last_denied '
            '| sort -denials'
        ),
        owned_by="access",
        expected_columns=[
            "principal_email", "denials", "methods", "resources", "first_denied", "last_denied"
        ],
    ),
    QueryTemplate(
        name="access_policy_changes_for_affected_resources",
        purpose="SetIamPolicy / policy mutations affecting the resources that later showed permission denials.",
        spl=(
            'search index=cloud_audit sourcetype=cloud_audit method=SetIamPolicy '
            '| eval change_time=strftime(_time, "%Y-%m-%dT%H:%M:%SZ") '
            '| table change_time, resource, principal_email, delta, request_id '
            '| sort -change_time'
        ),
        owned_by="access",
        expected_columns=["change_time", "resource", "principal_email", "delta", "request_id"],
    ),
]


ACCESS_SPEC = SpecialistSpec(
    name="access",
    title="Access / Security Investigator",
    goal="Identify permission and policy events that may explain or contextualize the incident.",
    lead_question="Who can do what, and did that change?",
    sub_questions=[
        "What IAM binding changes landed in or shortly before the incident window?",
        "Which principals are seeing permission denials, on which resources?",
        "Do any policy changes (SetIamPolicy) line up with resources later denied?",
        "Is the affected principal the same one whose binding was changed?",
    ],
    query_repertoire=ACCESS_QUERIES,
    output_tags=[
        "change:iam_binding",
        "change:policy",
        "denial:permission",
        "principal:*",
        "resource:*",
        "role:*",
    ],
)
