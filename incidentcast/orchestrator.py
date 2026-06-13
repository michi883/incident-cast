"""Parallel orchestration of specialists against a single incident."""

from __future__ import annotations

import asyncio
from typing import Iterable

from .specialists.base import Finding, IncidentContext, SpecialistName
from .specialists.runtime import Specialist


async def run_specialists(
    specialists: Iterable[Specialist],
    incident: IncidentContext,
) -> dict[SpecialistName, list[Finding]]:
    """Run each specialist's ``investigate()`` in parallel via ``asyncio.gather``."""

    specs = list(specialists)
    results = await asyncio.gather(
        *(s.investigate(incident) for s in specs),
        return_exceptions=True,
    )
    out: dict[SpecialistName, list[Finding]] = {}
    for specialist, result in zip(specs, results):
        if isinstance(result, BaseException):
            # Surface the failure but don't take down the whole investigation.
            print(f"[!] {specialist.spec.name} failed: {result!r}")
            out[specialist.spec.name] = []
        else:
            out[specialist.spec.name] = result
    return out
