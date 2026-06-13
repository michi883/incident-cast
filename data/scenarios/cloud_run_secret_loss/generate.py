"""Generate synthetic events for the cloud_run_secret_loss scenario.

Emits a stream of JSON lines to stdout, each line a HEC event payload with
``index``, ``sourcetype``, ``source``, ``time``, and ``event``. ``ingest.py``
consumes this stream and POSTs to Splunk's HEC.

Event mix:
  - app_logs / access_log:      per-request access entries with status, latency
  - app_logs / app_log:         error log lines (PermissionDenied etc.)
  - deploys / cloud_run_deploy: revision deploys
  - iam_changes / iam_binding:  IAM policy mutations
  - cloud_audit / cloud_audit:  audit-log records correlating to the IAM change

The numbers and timing line up with the M1 fixtures so that Reliability's
findings against this data should match the fixture-driven output.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

random.seed(42)

SCENARIO_PATH = Path(__file__).parent / "scenario.yaml"
TOGGLES_PATH = Path(__file__).parent / "toggles.json"

DEFAULT_TOGGLES: dict[str, bool] = {
    "deploy_new_revision": True,
    "remove_secret_access": True,
    "traffic_spike": True,
    "regional_failure": True,
    "downstream_impact": True,
    "rollback_revision": False,
}


def _load_toggles() -> dict[str, bool]:
    if not TOGGLES_PATH.exists():
        return dict(DEFAULT_TOGGLES)
    try:
        raw = json.loads(TOGGLES_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_TOGGLES)
    out = dict(DEFAULT_TOGGLES)
    for k, v in raw.items():
        if k in out and isinstance(v, bool):
            out[k] = v
    return out


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit(event: dict, *, index: str, sourcetype: str, source: str, t: datetime) -> None:
    payload = {
        "time": t.timestamp(),
        "index": index,
        "sourcetype": sourcetype,
        "source": source,
        "host": event.get("host", "cloud-run"),
        "event": event,
    }
    sys.stdout.write(json.dumps(payload) + "\n")


def _gen_access_logs(cfg: dict, toggles: dict[str, bool]) -> None:
    start = datetime.fromisoformat(cfg["window_start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(cfg["window_end"].replace("Z", "+00:00"))
    incident = datetime.fromisoformat(cfg["incident_at"].replace("Z", "+00:00"))
    rps_per_min = cfg["baseline_rps"] * 60
    # Write endpoints depend on the Stripe secret and fail post-incident; reads (/orders) and
    # /healthz don't, which lets Blast Radius bound the fault to the checkout write path.
    write_endpoints = ["/checkout/process", "/checkout/confirm"]
    endpoints = write_endpoints + ["/orders", "/healthz"]
    endpoint_weights = [0.45, 0.25, 0.20, 0.10]
    tenants = cfg["tenants"]
    rev_before = cfg["revision_before"]
    rev_after = cfg["revision_after"]
    deploy_at = datetime.fromisoformat(cfg["deploy_at"].replace("Z", "+00:00"))
    # If the secret-access removal didn't happen, the new revision still works:
    # error_rate stays at baseline post-incident. If the new revision wasn't
    # deployed at all, no revision-bound failure occurs either.
    failure_active = toggles["remove_secret_access"] and toggles["deploy_new_revision"]

    minute = start
    while minute < end:
        post_incident = minute >= incident and failure_active
        error_rate = cfg["post_error_rate"] if post_incident else cfg["baseline_error_rate"]
        p50 = cfg["post_latency_p50_ms"] if post_incident else cfg["baseline_latency_p50_ms"]
        p99 = cfg["post_latency_p99_ms"] if post_incident else cfg["baseline_latency_p99_ms"]
        traffic_mult = 1.0
        if toggles["traffic_spike"] and minute >= incident:
            traffic_mult = 1.5
        n = int(rps_per_min * traffic_mult) + random.randint(-30, 30)
        for _ in range(n):
            offset = random.uniform(0, 60)
            t = minute + timedelta(seconds=offset)
            rev = rev_after if t >= deploy_at else rev_before
            endpoint = random.choices(endpoints, weights=endpoint_weights)[0]
            tenant = random.choice(tenants)
            # Only checkout writes touch the secret, so only they fail post-incident.
            # /orders (read) stays at baseline; /healthz never errors.
            if endpoint == "/healthz":
                is_error = False
            elif endpoint in write_endpoints:
                is_error = random.random() < error_rate
            else:
                is_error = random.random() < cfg["baseline_error_rate"]
            status = 200
            if is_error:
                status = random.choices([500, 503], weights=[0.92, 0.08])[0]
            # latency: lognormal-ish distribution anchored on p50 / p99.
            r = random.random()
            if r < 0.5:
                latency = int(random.uniform(p50 * 0.6, p50 * 1.4))
            elif r < 0.95:
                latency = int(random.uniform(p50 * 1.4, p99 * 0.6))
            else:
                latency = int(random.uniform(p99 * 0.7, p99 * 1.4))
            if toggles["regional_failure"]:
                region = cfg["region"]
            else:
                region = random.choice([cfg["region"], "us-east1", "eu-west1"])
            event = {
                "service": cfg["service"],
                "env": cfg["env"],
                "region": region,
                "revision": rev,
                "endpoint": endpoint,
                "method": "POST" if endpoint in write_endpoints else "GET",
                "status": status,
                "latency_ms": latency,
                "tenant": tenant,
                "host": f"cloud-run-{cfg['service']}",
            }
            _emit(event, index="app_logs", sourcetype="access_log", source="cloud_run/access", t=t)
        minute += timedelta(minutes=1)

    # Healthy baseline traffic in other regions, so Blast Radius can show the failure is
    # confined to us-central1 rather than global.
    for region in cfg.get("healthy_regions", []):
        minute = start
        while minute < end:
            for _ in range(int(rps_per_min * 0.4)):
                offset = random.uniform(0, 60)
                t = minute + timedelta(seconds=offset)
                endpoint = random.choices(endpoints, weights=endpoint_weights)[0]
                is_error = endpoint != "/healthz" and random.random() < cfg["baseline_error_rate"]
                status = random.choices([500, 503], weights=[0.92, 0.08])[0] if is_error else 200
                _emit(
                    {
                        "service": cfg["service"],
                        "env": cfg["env"],
                        "region": region,
                        "revision": rev_after if minute >= deploy_at else rev_before,
                        "endpoint": endpoint,
                        "method": "POST" if endpoint in write_endpoints else "GET",
                        "status": status,
                        "latency_ms": int(random.uniform(40, 200)),
                        "tenant": random.choice(tenants),
                        "host": f"cloud-run-{cfg['service']}",
                    },
                    index="app_logs",
                    sourcetype="access_log",
                    source="cloud_run/access",
                    t=t,
                )
            minute += timedelta(minutes=1)


def _gen_app_errors(cfg: dict, toggles: dict[str, bool]) -> None:
    if not (toggles["remove_secret_access"] and toggles["deploy_new_revision"]):
        # No revision-bound permission failure: only baseline INFO logs.
        start = datetime.fromisoformat(cfg["window_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(cfg["window_end"].replace("Z", "+00:00"))
        t = start
        while t < end:
            _emit(
                {
                    "service": cfg["service"],
                    "env": cfg["env"],
                    "level": "INFO",
                    "message": "checkout processed",
                    "revision": cfg["revision_after"] if toggles["deploy_new_revision"] else cfg["revision_before"],
                },
                index="app_logs",
                sourcetype="app_log",
                source="cloud_run/app",
                t=t,
            )
            t += timedelta(seconds=30)
        return
    _gen_app_errors_impl(cfg)


def _gen_app_errors_impl(cfg: dict) -> None:
    incident = datetime.fromisoformat(cfg["incident_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(cfg["window_end"].replace("Z", "+00:00"))
    rev = cfg["revision_after"]
    secret = cfg["secret_resource"]

    # A handful of pre-incident benign INFO lines (baseline).
    start = datetime.fromisoformat(cfg["window_start"].replace("Z", "+00:00"))
    t = start
    while t < incident:
        _emit(
            {
                "service": cfg["service"],
                "env": cfg["env"],
                "level": "INFO",
                "message": "checkout processed",
                "revision": cfg["revision_before"] if t < datetime.fromisoformat(cfg["deploy_at"].replace("Z", "+00:00")) else rev,
            },
            index="app_logs",
            sourcetype="app_log",
            source="cloud_run/app",
            t=t,
        )
        t += timedelta(seconds=30)

    # After incident: heavy PermissionDenied + occasional DeadlineExceeded + a few InternalError.
    t = incident
    while t < end:
        # ~250 error lines/min total split across types
        for _ in range(220):
            offset = random.uniform(0, 60)
            tt = t + timedelta(seconds=offset)
            r = random.random()
            if r < 0.9:
                event = {
                    "service": cfg["service"],
                    "env": cfg["env"],
                    "level": "ERROR",
                    "error_type": "PermissionDenied",
                    "message": (
                        f"Permission 'secretmanager.versions.access' denied on resource "
                        f"'{secret}/versions/latest'"
                    ),
                    "revision": rev,
                    "service_account": cfg["service_account"],
                }
            elif r < 0.97:
                event = {
                    "service": cfg["service"],
                    "env": cfg["env"],
                    "level": "ERROR",
                    "error_type": "DeadlineExceeded",
                    "message": "context deadline exceeded calling secretmanager.googleapis.com",
                    "revision": rev,
                }
            else:
                event = {
                    "service": cfg["service"],
                    "env": cfg["env"],
                    "level": "ERROR",
                    "error_type": "InternalError",
                    "message": "checkout handler returned 500 without classified cause",
                    "revision": rev,
                }
            _emit(event, index="app_logs", sourcetype="app_log", source="cloud_run/app", t=tt)
        t += timedelta(minutes=1)


def _gen_deploys(cfg: dict, toggles: dict[str, bool]) -> None:
    # A small history of deploys before the incident-causing one.
    base = datetime.fromisoformat(cfg["deploy_at"].replace("Z", "+00:00"))
    history = [
        (base - timedelta(hours=6), "checkout-api-00039", "feat(checkout): refund webhook retries", "build-20260526-074512-7c11"),
        (base - timedelta(hours=2), "checkout-api-00040", "chore: bump base image", "build-20260526-114233-9a02"),
        (base - timedelta(minutes=45), "checkout-api-00041", "fix: idempotency-key hashing", "build-20260526-131655-b8d7"),
    ]
    if toggles["deploy_new_revision"]:
        history.append(
            (
                base,
                cfg["revision_after"],
                cfg.get("revision_after_commit", "chore: switch runtime service account"),
                cfg.get("revision_after_build", "ci-build-1192"),
            ),
        )
    for t, rev, message, build in history:
        _emit(
            {
                "service": cfg["service"],
                "env": cfg["env"],
                "region": cfg["region"],
                "revision": rev,
                "commit_message": message,
                "build_id": build,
                "actor": "deploybot@acme-prod.iam.gserviceaccount.com",
                "rollout": "100%",
                "rollback": False,
            },
            index="deploys",
            sourcetype="cloud_run_deploy",
            source="cloud_run/deploy",
            t=t,
        )
    if toggles["rollback_revision"]:
        # Emit a rollback deploy a few minutes after the incident.
        rb_at = base + timedelta(minutes=8)
        _emit(
            {
                "service": cfg["service"],
                "env": cfg["env"],
                "region": cfg["region"],
                "revision": cfg["revision_before"],
                "commit_message": "rollback: revert to last known good revision",
                "build_id": "ci-build-1193",
                "actor": "oncall@acme-prod.iam.gserviceaccount.com",
                "rollout": "100%",
                "rollback": True,
            },
            index="deploys",
            sourcetype="cloud_run_deploy",
            source="cloud_run/deploy",
            t=rb_at,
        )


def _gen_iam(cfg: dict, toggles: dict[str, bool]) -> None:
    if not toggles["remove_secret_access"]:
        return
    t = datetime.fromisoformat(cfg["iam_change_at"].replace("Z", "+00:00"))
    _emit(
        {
            "action": "remove",
            "role": "roles/secretmanager.secretAccessor",
            "member": f"serviceAccount:{cfg['service_account']}",
            "resource": cfg["secret_resource"],
            "actor": "iam-admin@acme-prod.iam.gserviceaccount.com",
            "actor_type": "user",
            "policy_id": "p-93f1",
            "change_reason": "cleanup of legacy bindings",
        },
        index="iam_changes",
        sourcetype="iam_binding_change",
        source="cloud_iam/policy",
        t=t,
    )
    # And a parallel cloud_audit entry for the same change.
    _emit(
        {
            "method": "SetIamPolicy",
            "resource": cfg["secret_resource"],
            "principal_email": "iam-admin@acme-prod.iam.gserviceaccount.com",
            "delta": {
                "removed": [
                    {
                        "role": "roles/secretmanager.secretAccessor",
                        "member": f"serviceAccount:{cfg['service_account']}",
                    }
                ]
            },
            "request_id": "req-7af20bc",
        },
        index="cloud_audit",
        sourcetype="cloud_audit",
        source="cloud_audit/secretmanager",
        t=t,
    )

    # A burst of post-incident audit "AccessSecretVersion" denials from the
    # affected service account.
    deny_start = datetime.fromisoformat(cfg["incident_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(cfg["window_end"].replace("Z", "+00:00"))
    tt = deny_start
    while tt < end:
        for _ in range(45):
            offset = random.uniform(0, 60)
            _emit(
                {
                    "method": "AccessSecretVersion",
                    "resource": cfg["secret_resource"] + "/versions/latest",
                    "principal_email": cfg["service_account"],
                    "status": "PERMISSION_DENIED",
                    "request_id": f"req-{random.randint(1000000, 9999999):07d}",
                },
                index="cloud_audit",
                sourcetype="cloud_audit",
                source="cloud_audit/secretmanager",
                t=tt + timedelta(seconds=offset),
            )
        tt += timedelta(minutes=1)


def _gen_downstream(cfg: dict, toggles: dict[str, bool]) -> None:
    if not toggles["downstream_impact"]:
        return
    if not (toggles["remove_secret_access"] and toggles["deploy_new_revision"]):
        return
    incident = datetime.fromisoformat(cfg["incident_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(cfg["window_end"].replace("Z", "+00:00"))
    for svc in cfg["downstream_services"]:
        t = incident
        while t < end:
            for _ in range(80):
                offset = random.uniform(0, 60)
                tt = t + timedelta(seconds=offset)
                # Downstream sees mostly 503s because checkout-api times out.
                _emit(
                    {
                        "service": svc,
                        "env": cfg["env"],
                        "region": cfg["region"],
                        "endpoint": "/internal/charge",
                        "status": 503,
                        "latency_ms": random.randint(300, 900),
                        "upstream": cfg["service"],
                    },
                    index="app_logs",
                    sourcetype="access_log",
                    source="cloud_run/access",
                    t=tt,
                )
            t += timedelta(minutes=1)


def main() -> None:
    cfg = yaml.safe_load(SCENARIO_PATH.read_text())
    toggles = _load_toggles()
    sys.stderr.write(f"toggles: {json.dumps(toggles)}\n")
    _gen_deploys(cfg, toggles)
    _gen_iam(cfg, toggles)
    _gen_access_logs(cfg, toggles)
    _gen_app_errors(cfg, toggles)
    _gen_downstream(cfg, toggles)


if __name__ == "__main__":
    main()
