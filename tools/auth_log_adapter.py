#!/usr/bin/env python3
"""Collect structured NAS authentication metadata as Warroom events."""

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
    "/var/log/auth.log",
    "/var/log/messages",
    "/var/log/synosys.log",
    "/var/log/synolog/synosys.log",
    "/var/log/synoscgi.log",
    "/var/log/samba/log.smbd",
    "/var/log/ftp.log",
    "/var/log/vsftpd.log",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd|token|session|cookie|authorization)=([^\s&]+)"),
    re.compile(r"(?i)(Cookie:|Authorization:)\s*\S+"),
]
IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
USER_PATTERNS = [
    re.compile(r"\b(?:Accepted|Failed)\s+\S+\s+for\s+(?:invalid user\s+)?(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\binvalid user\s+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\buser(?:name)?[=: \[]+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
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


def _redact(line: str) -> str:
    redacted = line
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
    return redacted[:1200]


def _service(log_path: Path, line: str) -> str:
    text = f"{log_path} {line}".lower()
    if "sshd" in text or log_path.name == "auth.log":
        return "ssh"
    if "samba" in text or "smb" in text:
        return "smb"
    if "ftp" in text or "vsftpd" in text:
        return "ftp"
    if "synowebapi" in text or "synoscgi" in text or "dsm" in text:
        return "dsm"
    return "system"


def _classification(line: str) -> tuple[str, str, str | None, float] | None:
    text = line.lower()
    if "accepted " in text or "login successful" in text or "logged in" in text:
        return "auth_success", "success", None, 0.88
    if "failed password" in text or "authentication failure" in text or "login failed" in text or "failed login" in text:
        return "auth_failure", "failure", "credential_failed", 0.9
    if "invalid user" in text:
        return "auth_failure", "failure", "invalid_user", 0.86
    if "too many authentication failures" in text or "blocked" in text or "lock" in text and "login" in text:
        return "auth_lockout", "failure", "lockout_or_block", 0.82
    if "session opened" in text:
        return "session_opened", "success", None, 0.76
    if "session closed" in text:
        return "session_closed", "success", None, 0.72
    return None


def _first_user(line: str) -> str | None:
    for pattern in USER_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group("user")
    return None


def _event_from_line(line: str, log_path: Path, line_no: int, nas_host: str) -> dict[str, Any] | None:
    classification = _classification(line)
    if classification is None:
        return None
    action, outcome, failure_reason, confidence = classification
    digest = hashlib.sha256(f"{log_path}:{line_no}:{line}".encode("utf-8", errors="replace")).hexdigest()[:24]
    source_ip_match = IP_RE.search(line)
    service = _service(log_path, line)
    event: dict[str, Any] = {
        "event_id": f"auth-log-{digest}",
        "action": action,
        "nas_host": nas_host,
        "source_channel": "auth_log",
        "source_app": "nas_auth",
        "source_surface": "auth_log_tail",
        "service": service,
        "network_protocol": "ssh" if service == "ssh" else service,
        "confidence": confidence,
        "observed_at": int(time.time()),
        "event_outcome": outcome,
        "failure_reason": failure_reason,
        "actor": _first_user(line),
        "source_ip": source_ip_match.group(0) if source_ip_match else None,
        "message_excerpt": _redact(line),
        "raw_ref": {
            "type": "log_line_ref",
            "path": str(log_path),
            "line_ref": str(line_no),
            "sha256_24": digest,
        },
        "policy_notes": [
            "Auth log adapter tails existing authentication-related logs through transient SSH payloads.",
            "Secrets are redacted before event normalization.",
        ],
    }
    return {key: value for key, value in event.items() if value is not None}


def read_auth_events(log_paths: list[Path], tail_lines: int, limit: int, nas_host: str) -> dict[str, Any]:
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
        return {"found": False, "stage": "auth_events_not_found", "inspected": inspected, "events": []}
    return {"found": True, "stage": "auth_events_normalized", "inspected": inspected, "events": events}


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
    command.extend([remote, "sudo", "-n", "python3", "-", "--mode", "local", "--nas-host", args.nas_host, "--tail-lines", str(args.tail_lines), "--limit", str(args.limit)])
    for path in args.log_path:
        command.extend(["--log-path", path])
    proc = subprocess.run(command, input=script_source, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
    if proc.returncode != 0:
        return {"found": False, "stage": "remote_auth_log_adapter_failed", "returncode": proc.returncode, "stderr": proc.stderr.strip()[-1000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"found": False, "stage": "remote_auth_log_adapter_invalid_json", "error": str(exc), "stdout_sample": proc.stdout[:1000]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--log-path", action="append", default=[], help="NAS auth log path to inspect")
    parser.add_argument("--tail-lines", type=int, default=2000)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--nas-host", default="rawdb")
    parser.add_argument("--host", default="rawdb", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="", help="SSH user for --mode remote; empty uses ssh config or current user")
    parser.add_argument("--timeout-sec", type=int, default=30)
    args = parser.parse_args()
    if args.limit < 1 or args.tail_lines < 1:
        print(json.dumps({"found": False, "stage": "invalid_limit_or_tail_lines"}, indent=2, sort_keys=True))
        return 2
    result = _run_remote(args) if args.mode == "remote" else read_auth_events([Path(path) for path in (args.log_path or DEFAULT_LOG_PATHS)], args.tail_lines, args.limit, args.nas_host)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
