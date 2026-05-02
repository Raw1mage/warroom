#!/usr/bin/env python3
"""Stream NAS service/system log metadata into Warroom Loki events.

This adapter uses SSH stdin payload execution for remote NAS collection. It
tails existing log files only, redacts common secret-bearing fragments, and does
not install persistent agents or read user file contents.
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
    "/var/log/nginx/access.log",
    "/var/log/nginx/error.log",
    "/var/log/httpd/access_log",
    "/var/log/httpd/error_log",
    "/var/log/rsyncd.log",
    "/var/log/ftp.log",
    "/var/log/vsftpd.log",
    "/var/log/auth.log",
    "/var/log/scemd.log",
    "/var/log/synoscgi.log",
    "/var/log/synoscheduler.log",
    "/var/log/synopkg.log",
    "/var/log/synolog/synosmb.log",
    "/var/log/synolog/synofile.log",
    "/var/log/synolog/synoshare.log",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd|token|session|cookie|authorization)=([^\s&]+)"),
    re.compile(r"(?i)(Cookie:|Authorization:)\s*\S+"),
]
IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
PATH_RE = re.compile(r"(?P<path>/(?:volume\d+/)?(?:homes?|share|photo|music|video|web|docker|var|tmp)[^\s\"'<>]*)")
USER_PATTERNS = [
    re.compile(r"\buser(?:name)?[=: ]+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\baccount[=: ]+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\bfor\s+user\s+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
    re.compile(r"\b(?:Accepted|Failed)\s+\S+\s+for\s+(?P<user>[A-Za-z0-9._@-]+)", re.IGNORECASE),
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
        redacted = pattern.sub(lambda m: f"{m.group(1)}=<redacted>", redacted)
    return redacted[:1200]


def _service(log_path: Path, line: str) -> tuple[str, str]:
    text = f"{log_path} {line}".lower()
    if "samba" in text or "smb" in text or "cifs" in text:
        return "smb", "smb"
    if "nginx" in text:
        return "nginx", "http"
    if "httpd" in text or "apache" in text:
        return "httpd", "http"
    if "ftp" in text or "vsftpd" in text:
        return "ftp", "ftp"
    if "rsync" in text:
        return "rsync", "rsync"
    if "ssh" in text or "sshd" in text or log_path.name == "auth.log":
        return "ssh", "ssh"
    if "synoscgi" in text or "synosys" in text or "dsm" in text:
        return "dsm", "http"
    return "system", "nas_log"


def _action(line: str, has_path: bool) -> tuple[str, float]:
    text = line.lower()
    if has_path and any(token in text for token in ["delete", "unlink", "remove", "removed"]):
        return "file_delete", 0.66
    if has_path and any(token in text for token in ["rename", "renamed", "move", "moved"]):
        return "file_rename", 0.64
    if has_path and any(token in text for token in ["write", "modify", "modified", "upload", " put "]):
        return "file_write", 0.62
    if has_path and any(token in text for token in ["download", " read", "open", " get "]):
        return "file_read", 0.58
    if any(token in text for token in ["login", "accepted", "failed", "session opened", "session closed"]):
        return "auth_activity", 0.70
    if "error" in text or "fail" in text:
        return "service_error", 0.60
    return "system_log", 0.50


def _first_user(line: str) -> str | None:
    for pattern in USER_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group("user")
    return None


def _event_from_line(line: str, log_path: Path, line_no: int, nas_host: str) -> dict[str, Any]:
    digest = hashlib.sha256(f"{log_path}:{line_no}:{line}".encode("utf-8", errors="replace")).hexdigest()[:24]
    service, protocol = _service(log_path, line)
    path_match = PATH_RE.search(line)
    display_path = path_match.group("path") if path_match else None
    action, confidence = _action(line, display_path is not None)
    source_ip_match = IP_RE.search(line)
    file_name = os.path.basename(display_path.rstrip("/")) if display_path else None
    event: dict[str, Any] = {
        "event_id": f"nas-system-log-{digest}",
        "action": action,
        "nas_host": nas_host,
        "source_channel": "nas_system_log",
        "source_app": f"nas_{service}",
        "source_surface": "nas_system_log_tail",
        "service": service,
        "protocol": protocol,
        "network_protocol": protocol if protocol != "nas_log" else None,
        "confidence": confidence,
        "observed_at": int(time.time()),
        "actor": _first_user(line),
        "source_ip": source_ip_match.group(0) if source_ip_match else None,
        "display_path": display_path,
        "file_name": file_name,
        "folder_path": os.path.dirname(display_path) if display_path else None,
        "object_type": "file" if display_path else "log_line",
        "message_excerpt": _redact(line),
        "raw_ref": {
            "type": "log_line_ref",
            "path": str(log_path),
            "line_ref": str(line_no),
            "sha256_24": digest,
        },
        "policy_notes": [
            "NAS system log adapter tails existing service logs through transient SSH payloads.",
            "Log content is redacted for common secret-bearing fragments before Loki push.",
            "This source is service-log evidence, not guaranteed kernel-level per-file read auditing.",
        ],
    }
    return {key: value for key, value in event.items() if value is not None}


def read_system_log_events(log_paths: list[Path], tail_lines: int, limit: int, nas_host: str) -> dict[str, Any]:
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
            if not line.strip():
                continue
            events.append(_event_from_line(line, log_path, base_line_no + offset, nas_host))
            if len(events) >= limit:
                break
        if len(events) >= limit:
            break
    if not events:
        return {"found": False, "stage": "nas_system_log_events_not_found", "inspected": inspected, "events": []}
    return {"found": True, "stage": "nas_system_log_events_normalized", "inspected": inspected, "events": events}


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
        return {"found": False, "stage": "remote_system_log_adapter_failed", "returncode": proc.returncode, "stderr": proc.stderr.strip()[-1000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"found": False, "stage": "remote_system_log_adapter_invalid_json", "error": str(exc), "stdout_sample": proc.stdout[:1000]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--log-path", action="append", default=[], help="NAS log file path to inspect")
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

    if args.mode == "remote":
        result = _run_remote(args)
    else:
        log_paths = [Path(path) for path in (args.log_path or DEFAULT_LOG_PATHS)]
        result = read_system_log_events(log_paths, args.tail_lines, args.limit, args.nas_host)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
