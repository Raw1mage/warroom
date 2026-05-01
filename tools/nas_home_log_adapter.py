#!/usr/bin/env python3
"""Read NAS home-scope audit/log metadata as Warroom DLP events.

This helper inspects existing NAS log files for metadata-only evidence that
references `/home`, `/homes`, or `/volume*/homes` paths. It never reads file
contents and does not install a persistent NAS-side agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATHS = [
    "/var/log/messages",
    "/var/log/synosys.log",
    "/var/log/synolog/synosys.log",
    "/var/log/samba/log.smbd",
    "/var/log/samba/log.nmbd",
    "/var/log/samba/log.winbindd",
    "/var/log/rsyncd.log",
    "/var/log/ftp.log",
    "/var/log/vsftpd.log",
    "/var/log/auth.log",
]

HOME_SCOPE_RE = re.compile(r"(?P<path>/(?:volume\d+/)?homes?/[^\s\"'<>]+|/home/[^\s\"'<>]+)")
IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
USER_PATTERNS = [
    re.compile(r"\buser(?:name)?[=: ]+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\baccount[=: ]+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\bfor\s+user\s+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
]


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            block_size = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= max_lines:
                read_size = min(block_size, size)
                size -= read_size
                handle.seek(size)
                data = handle.read(read_size) + data
        return data.decode("utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return []


def _classify_protocol(log_path: Path, line: str) -> str:
    text = f"{log_path} {line}".lower()
    if "samba" in text or "smb" in text or "cifs" in text:
        return "smb"
    if "nfs" in text:
        return "nfs"
    if "ftp" in text or "vsftpd" in text:
        return "ftp"
    if "rsync" in text:
        return "rsync"
    if "webdav" in text:
        return "webdav"
    if "ssh" in text or "sftp" in text:
        return "sftp"
    return "nas_log"


def _classify_action(line: str) -> tuple[str, float, str]:
    text = line.lower()
    if any(token in text for token in ["delete", "unlink", "removed", "remove "]):
        return "file_delete", 0.72, "delete_keyword"
    if any(token in text for token in ["rename", "renamed", "move ", "moved"]):
        return "file_rename", 0.70, "rename_keyword"
    if any(token in text for token in ["write", "modified", "modify", "upload", "put "]):
        return "file_write", 0.66, "write_keyword"
    if any(token in text for token in ["download", "read", "open", "get "]):
        return "file_read", 0.60, "read_keyword"
    return "file_activity", 0.45, "home_path_log_match"


def _first_ip(line: str) -> str | None:
    match = IP_RE.search(line)
    return match.group(0) if match else None


def _first_user(line: str) -> str | None:
    for pattern in USER_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group("user")
    return None


def _event_from_line(line: str, log_path: Path, line_no: int, nas_host: str) -> dict[str, Any] | None:
    path_match = HOME_SCOPE_RE.search(line)
    if not path_match:
        return None
    display_path = path_match.group("path")
    file_name = os.path.basename(display_path.rstrip("/")) or None
    folder_path = os.path.dirname(display_path) or None
    digest = hashlib.sha256(f"{log_path}:{line_no}:{line}".encode("utf-8", errors="replace")).hexdigest()[:24]
    action, confidence, action_reason = _classify_action(line)
    protocol = _classify_protocol(log_path, line)

    event: dict[str, Any] = {
        "event_id": f"nas-home-log-{digest}",
        "action": action,
        "nas_host": nas_host,
        "source_channel": "nas_home_log",
        "source_app": "nas_file_service",
        "source_surface": "nas_home_scope_log",
        "object_type": "file" if file_name else "path",
        "protocol": protocol,
        "network_protocol": protocol if protocol != "nas_log" else None,
        "confidence": confidence,
        "observed_at": int(time.time()),
        "actor": _first_user(line),
        "source_ip": _first_ip(line),
        "file_name": file_name,
        "folder_path": folder_path,
        "display_path": display_path,
        "extension": os.path.splitext(file_name or "")[1].lower() if file_name else None,
        "correlation_refs": [
            {
                "type": "nas_home_log_line",
                "path": str(log_path),
                "line_ref": str(line_no),
                "action_reason": action_reason,
            }
        ],
        "raw_ref": {
            "type": "log_line_ref",
            "path": str(log_path),
            "line_ref": str(line_no),
            "sha256_24": digest,
        },
        "policy_notes": [
            "NAS home log adapter reads existing log metadata only.",
            "Only log lines referencing configured home-scope paths are normalized.",
            "File content, cookies, session tokens, credentials, and raw credential-bearing URLs remain forbidden.",
        ],
    }
    return {key: value for key, value in event.items() if value is not None}


def read_home_log_events(log_paths: list[Path], tail_lines: int, limit: int, nas_host: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []
    for log_path in log_paths:
        if not log_path.is_file():
            inspected.append({"path": str(log_path), "readable": False, "reason": "missing_or_not_file"})
            continue
        lines = _tail_lines(log_path, tail_lines)
        inspected.append({"path": str(log_path), "readable": bool(lines), "tail_lines": len(lines)})
        base_line_no = max(1, tail_lines - len(lines) + 1)
        for offset, line in enumerate(lines):
            event = _event_from_line(line, log_path, base_line_no + offset, nas_host)
            if event:
                events.append(event)
            if len(events) >= limit:
                break
        if len(events) >= limit:
            break

    if not events:
        return {
            "found": False,
            "stage": "home_scope_log_events_not_found",
            "log_paths": [str(path) for path in log_paths],
            "inspected": inspected,
            "events": [],
        }
    return {
        "found": True,
        "stage": "home_scope_log_events_normalized",
        "log_paths": [str(path) for path in log_paths],
        "inspected": inspected,
        "events": events,
    }


def _run_remote(args: argparse.Namespace) -> dict[str, Any]:
    script_source = Path(__file__).read_text(encoding="utf-8")
    remote = f"{args.user}@{args.host}" if args.user else args.host
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={min(args.timeout_sec, 30)}",
        remote,
        "sudo",
        "-n",
        "python3",
        "-",
        "--mode",
        "local",
        "--nas-host",
        args.nas_host,
        "--tail-lines",
        str(args.tail_lines),
        "--limit",
        str(args.limit),
    ]
    for path in args.log_path:
        command.extend(["--log-path", path])
    proc = subprocess.run(command, input=script_source, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
    if proc.returncode != 0:
        return {
            "found": False,
            "stage": "remote_home_log_adapter_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[-1000:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "found": False,
            "stage": "remote_home_log_adapter_invalid_json",
            "error": str(exc),
            "stdout_sample": proc.stdout[:1000],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--log-path", action="append", default=[], help="NAS log file path to inspect")
    parser.add_argument("--tail-lines", type=int, default=2000)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--nas-host", default="rawdb")
    parser.add_argument("--host", default="rawdb", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="", help="SSH user for --mode remote; empty uses ssh config or current user")
    parser.add_argument("--timeout-sec", type=int, default=30)
    args = parser.parse_args()

    if args.limit < 1 or args.tail_lines < 1:
        print(json.dumps({"found": False, "stage": "invalid_limit_or_tail_lines"}, indent=2, sort_keys=True))
        return 2

    if args.mode == "remote":
        result = _run_remote(args)
    else:
        log_paths = [Path(path) for path in (args.log_path or DEFAULT_LOG_PATHS)]
        result = read_home_log_events(log_paths, args.tail_lines, args.limit, args.nas_host)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
