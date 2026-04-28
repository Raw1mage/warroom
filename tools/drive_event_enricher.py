#!/usr/bin/env python3
"""Build a readable Warroom DLP event from a Synology Drive file_id.

This helper keeps the current least-intrusive model:

- Warroom runs locally.
- The Drive resolver is streamed to the NAS over SSH stdin.
- The NAS opens Synology Drive SQLite databases read-only.
- No helper script is installed on the NAS.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


RESOLVER_PATH = Path(__file__).with_name("drive_file_resolver.py")


def _run_remote_resolver(host: str, user: str, permanent_id: int, timeout_sec: int) -> dict[str, Any]:
    resolver_source = RESOLVER_PATH.read_text(encoding="utf-8")
    remote = f"{user}@{host}"
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={min(timeout_sec, 30)}",
            remote,
            "sudo",
            "-n",
            "python3",
            "-",
            str(permanent_id),
        ],
        input=resolver_source,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "found": False,
            "stage": "remote_resolver_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[-1000:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "found": False,
            "stage": "remote_resolver_invalid_json",
            "error": str(exc),
            "stdout_sample": proc.stdout[:1000],
        }


def build_event(args: argparse.Namespace, resolved: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": f"drive-{args.action}-{args.permanent_id}",
        "action": args.action,
        "nas_host": args.nas_host,
        "source_channel": ["web_ingress_nginx", "drive_db"],
        "source_app": "synology_drive",
        "source_surface": "drive_web_viewer",
        "file_object_id": str(args.permanent_id),
        "confidence": args.confidence,
        "duration_confidence": args.duration_confidence,
        "view_started_at": args.view_started_at,
        "view_last_seen_at": args.view_last_seen_at,
        "estimated_view_duration_sec": args.estimated_view_duration_sec,
        "correlation_refs": [
            {
                "type": "drive_ssh_readonly_resolver",
                "description": "Warroom streamed the Drive resolver over SSH stdin and opened Drive SQLite databases read-only on the NAS.",
            }
        ],
        "policy_notes": [
            "Human-readable metadata is allowed in Warroom internal management evidence.",
            "File content, cookies, session tokens, credentials, and raw credential-bearing URLs remain forbidden.",
        ],
    }

    if resolved.get("found"):
        for key in [
            "view_id",
            "node_id",
            "parent_id",
            "file_type",
            "file_name",
            "folder_path",
            "display_path",
            "extension",
            "size_bytes",
            "ctime",
            "mtime",
            "access_time",
            "parent_permanent_id",
            "chain",
        ]:
            if key in resolved:
                event[key] = resolved[key]
    else:
        event["confidence"] = min(args.confidence, 0.25)
        event["resolver_error"] = resolved

    return event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("permanent_id", type=int, help="Synology Drive permanent_id/file_id")
    parser.add_argument("--host", default="nas.example.local", help="SSH host alias or address")
    parser.add_argument("--user", default="nas-admin", help="SSH user")
    parser.add_argument("--nas-host", default="demo-nas", help="Warroom NAS inventory alias")
    parser.add_argument("--action", default="webapp_file_preview", help="Normalized DLP action")
    parser.add_argument("--confidence", type=float, default=0.78)
    parser.add_argument("--duration-confidence", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--view-started-at", default=None)
    parser.add_argument("--view-last-seen-at", default=None)
    parser.add_argument("--estimated-view-duration-sec", type=int, default=None)
    parser.add_argument("--timeout-sec", type=int, default=30)
    args = parser.parse_args()

    resolved = _run_remote_resolver(args.host, args.user, args.permanent_id, args.timeout_sec)
    event = build_event(args, resolved)
    print(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if resolved.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
