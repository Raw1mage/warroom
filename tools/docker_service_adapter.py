#!/usr/bin/env python3
"""Collect bounded Docker service health metadata as Warroom events."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def _run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def _docker_command() -> list[str]:
    if _run(["sh", "-c", "command -v docker >/dev/null 2>&1"], timeout=5).returncode == 0:
        return ["docker"]
    return []


def _parse_ps_line(line: str) -> dict[str, Any] | None:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    names = str(row.get("Names") or row.get("Name") or "").strip()
    state = str(row.get("State") or "").strip().lower()
    status = str(row.get("Status") or "").strip()
    health = "unknown"
    status_lower = status.lower()
    if "(healthy)" in status_lower:
        health = "healthy"
    elif "(unhealthy)" in status_lower:
        health = "unhealthy"
    elif state == "running":
        health = "running_no_healthcheck"
    elif state:
        health = state
    return {
        "container_id": str(row.get("ID") or "").strip(),
        "container_name": names,
        "image": str(row.get("Image") or "").strip(),
        "state": state or "unknown",
        "status": status,
        "health": health,
    }


def collect_docker_services(nas_host: str, limit: int) -> dict[str, Any]:
    docker = _docker_command()
    if not docker:
        return {"found": False, "stage": "docker_cli_missing", "events": []}
    proc = _run(docker + ["ps", "-a", "--no-trunc", "--format", "{{json .}}"], timeout=30)
    if proc.returncode != 0:
        return {
            "found": False,
            "stage": "docker_ps_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[-1000:],
            "events": [],
        }
    rows = [_parse_ps_line(line) for line in proc.stdout.splitlines() if line.strip()]
    containers = [row for row in rows if row is not None]
    observed_at = int(time.time())
    unhealthy = [row for row in containers if row["health"] in {"unhealthy", "exited", "dead", "restarting"} or row["state"] != "running"]
    event: dict[str, Any] = {
        "event_id": f"docker-service-{nas_host}-{observed_at}",
        "action": "docker_service_snapshot",
        "nas_host": nas_host,
        "source_channel": "docker_service",
        "source_app": "host_docker",
        "source_surface": "ssh_transient_payload",
        "confidence": 0.95,
        "observed_at": observed_at,
        "docker_container_count": len(containers),
        "docker_running_count": sum(1 for row in containers if row["state"] == "running"),
        "docker_healthy_count": sum(1 for row in containers if row["health"] == "healthy"),
        "docker_unhealthy_count": len(unhealthy),
        "docker_containers": containers[: max(1, limit)],
        "docker_unhealthy_containers": unhealthy[: max(1, limit)],
        "policy_notes": [
            "Docker service adapter reads docker ps metadata only.",
            "Container details are bounded inside event payload and are not emitted as Loki labels.",
        ],
    }
    return {"found": True, "stage": "docker_service_snapshot", "events": [event]}


def _run_remote(args: argparse.Namespace) -> dict[str, Any]:
    script_source = Path(__file__).read_text(encoding="utf-8")
    remote = f"{args.user}@{args.host}" if args.user else args.host
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={min(args.timeout_sec, 30)}",
    ]
    identity_file = os.environ.get("WARROOM_SSH_IDENTITY_FILE", "").strip()
    if identity_file:
        command.extend(["-o", f"IdentityFile={identity_file}", "-o", "IdentitiesOnly=yes"])
    command.extend([remote, "sudo", "-n", "python3", "-", "--mode", "local", "--nas-host", args.nas_host, "--limit", str(args.limit)])
    proc = subprocess.run(command, input=script_source, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
    if proc.returncode != 0:
        return {"found": False, "stage": "remote_docker_service_adapter_failed", "returncode": proc.returncode, "stderr": proc.stderr.strip()[-1000:], "events": []}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"found": False, "stage": "remote_docker_service_adapter_invalid_json", "error": str(exc), "stdout_sample": proc.stdout[:1000], "events": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--nas-host", default="unraid")
    parser.add_argument("--host", default="unraid", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="", help="SSH user for --mode remote; empty uses ssh config or current user")
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1:
        print(json.dumps({"found": False, "stage": "invalid_limit", "events": []}, indent=2, sort_keys=True))
        return 2
    result = _run_remote(args) if args.mode == "remote" else collect_docker_services(args.nas_host, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
