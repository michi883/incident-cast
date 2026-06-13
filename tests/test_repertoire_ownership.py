"""Enforces that the specialists are structurally distinct.

Fails if:
- any ``QueryTemplate`` is claimed by more than one specialist
- any specialist's spec contains a template owned by a different specialist
- two specialists declare the same query name

This codifies the user-feedback rule: specialists are not "the same LLM with
different prompts" — they have non-overlapping query repertoires.
"""

from __future__ import annotations

from incidentcast.specialists.access import ACCESS_SPEC
from incidentcast.specialists.base import QueryTemplate
from incidentcast.specialists.blast_radius import BLAST_RADIUS_SPEC
from incidentcast.specialists.deployment import DEPLOYMENT_SPEC
from incidentcast.specialists.reliability import RELIABILITY_SPEC

ALL_SPECS = [
    RELIABILITY_SPEC,
    DEPLOYMENT_SPEC,
    BLAST_RADIUS_SPEC,
    ACCESS_SPEC,
]


def test_each_template_has_exactly_one_owner() -> None:
    template_owners: dict[str, list[str]] = {}
    for spec in ALL_SPECS:
        for tpl in spec.query_repertoire:
            template_owners.setdefault(tpl.name, []).append(spec.name)
    duplicates = {name: owners for name, owners in template_owners.items() if len(owners) > 1}
    assert not duplicates, (
        f"Query templates with multiple owners: {duplicates}. "
        f"Each template must belong to exactly one specialist."
    )


def test_template_owned_by_matches_spec() -> None:
    for spec in ALL_SPECS:
        for tpl in spec.query_repertoire:
            assert tpl.owned_by == spec.name, (
                f"Template '{tpl.name}' appears in {spec.name}'s repertoire but "
                f"declares owned_by={tpl.owned_by!r}. Fix the QueryTemplate."
            )


def test_no_template_name_collisions_across_specialists() -> None:
    seen: dict[str, str] = {}
    for spec in ALL_SPECS:
        for tpl in spec.query_repertoire:
            if tpl.name in seen and seen[tpl.name] != spec.name:
                raise AssertionError(
                    f"Template name collision: '{tpl.name}' in both "
                    f"{seen[tpl.name]} and {spec.name}"
                )
            seen[tpl.name] = spec.name


def test_query_template_namespace_convention() -> None:
    """Each template name must start with its owner's prefix.

    This makes the ownership relationship obvious at the call site and
    prevents accidental ports of templates between specialists.
    """
    for spec in ALL_SPECS:
        for tpl in spec.query_repertoire:
            assert tpl.name.startswith(f"{spec.name}_"), (
                f"Template '{tpl.name}' must be prefixed with '{spec.name}_' "
                f"to make ownership visible."
            )


def test_querytemplate_is_immutable_value_type() -> None:
    """Sanity check: QueryTemplate is a frozen pydantic model in spirit.

    We don't freeze pydantic V2 models by default, but we should never mutate
    them after construction. This test just confirms the model behaves like a
    value type by being constructible from kwargs.
    """
    tpl = QueryTemplate(
        name="reliability_smoke",
        purpose="smoke",
        spl="search index=x",
        owned_by="reliability",
        expected_columns=[],
    )
    assert tpl.name == "reliability_smoke"
    assert tpl.owned_by == "reliability"
