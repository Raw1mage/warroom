#!/usr/bin/env python3
"""Read Synology Drive activity DB rows as Warroom DLP events.

Read-only helper for `/volume1/@synologydrive/@sync`. It never reads file
contents and never installs code on the NAS when used through SSH.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_SYNC_ROOT = "/volume1/@synologydrive/@sync"


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _int_value(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if not text or not text.lstrip("-").isdigit():
        return None
    return int(text)


def _classify_action(drive_type: int | None, client_type: int | None, node_found: bool) -> tuple[str, float, str]:
    if drive_type == 23 and client_type == 256:
        return "webapp_file_download", 0.86, "drive_web_download_candidate"
    if drive_type == 24 and client_type == 256:
        return "webapp_file_preview", 0.78, "drive_web_preview_candidate"
    if node_found:
        return "drive_file_activity", 0.64, "drive_activity_with_node_metadata"
    return "drive_file_activity", 0.45, "drive_activity_without_node_metadata"


def _view_db(sync_root: Path, view_id: int | None) -> Path | None:
    if view_id is None:
        return None
    path = sync_root / "view" / str(view_id) / "view-db.sqlite"
    return path if path.is_file() else None


def _node_by_id(conn: sqlite3.Connection, node_id: int) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute(
            "SELECT node_id, parent_id, file_type, name, extension, v_file_size, "
            "permanent_id, parent_permanent_id, ctime, mtime, access_time "
            "FROM node_table WHERE node_id = ?",
            (node_id,),
        ).fetchone()
    )


def _resolve_node(sync_root: Path, view_id: int | None, node_id: int | None) -> dict[str, Any] | None:
    db_path = _view_db(sync_root, view_id)
    if db_path is None or node_id is None:
        return None
    try:
        with _connect_ro(db_path) as conn:
            node = _node_by_id(conn, node_id)
            if node is None:
                return None
            chain = []
            current = node
            seen_node_ids = set()
            while current is not None:
                current_node_id = current.get("node_id")
                if current_node_id in seen_node_ids:
                    break
                seen_node_ids.add(current_node_id)
                chain.append(current)
                parent_id = current.get("parent_id")
                if parent_id in (None, 0):
                    break
                current = _node_by_id(conn, int(parent_id))
    except sqlite3.Error:
        return None

    ordered_chain = list(reversed(chain))
    path_parts = [str(item["name"]) for item in ordered_chain if item.get("name")]
    display_path = "/" + "/".join(path_parts) if path_parts else None
    folder_path = "/" + "/".join(path_parts[:-1]) if len(path_parts) > 1 else "/" if path_parts else None
    file_name = str(node.get("name") or "") or None
    extension = node.get("extension") or os.path.splitext(file_name or "")[1].lower()
    size_value = node.get("v_file_size")

    return {
        "view_db": str(db_path),
        "node_id": node.get("node_id"),
        "parent_id": node.get("parent_id"),
        "file_type": node.get("file_type"),
        "permanent_id": node.get("permanent_id"),
        "parent_permanent_id": node.get("parent_permanent_id"),
        "file_name": file_name,
        "folder_path": folder_path,
        "display_path": display_path,
        "extension": extension,
        "size_bytes": int(size_value) if isinstance(size_value, int) or str(size_value or "").isdigit() else None,
        "ctime": node.get("ctime"),
        "mtime": node.get("mtime"),
        "access_time": node.get("access_time"),
    }


def _event_from_log_row(sync_root: Path, row: dict[str, Any], nas_host: str, max_label_len: int) -> dict[str, Any]:
    drive_type = _int_value(row.get("type"))
    client_type = _int_value(row.get("client_type"))
    view_id = _int_value(row.get("view_id"))
    node_id = _int_value(row.get("p1"))
    node = _resolve_node(sync_root, view_id, node_id)
    action, confidence, action_reason = _classify_action(drive_type, client_type, node is not None)
    row_id = row.get("id")

    event: dict[str, Any] = {
        "event_id": f"drive-activity-{nas_host}-{view_id or 'unknown'}-{row_id or row.get('time')}",
        "action": action,
        "nas_host": nas_host,
        "source_channel": "drive_activity_db",
        "source_app": "synology_drive",
        "source_surface": "drive_log_db",
        "observed_at": row.get("time"),
        "actor": row.get("username") or None,
        "source_ip": row.get("ip_address") or None,
        "source_client_type": client_type,
        "source_drive_type": drive_type,
        "source_drive_action": action_reason,
        "view_id": view_id,
        "node_id": node_id,
        "network_protocol": "synology_drive",
        "confidence": confidence,
        "correlation_refs": [
            {
                "type": "drive_log_db_node_lookup",
                "path": str(sync_root / "log-db.sqlite"),
                "table": "log_table",
                "row_ref": str(row_id or "")[:max_label_len],
                "view_id": view_id,
                "node_id_source": "log_table.p1",
                "action_reason": action_reason,
            }
        ],
        "raw_ref": {
            "type": "sqlite_row_ref",
            "path": str(sync_root / "log-db.sqlite"),
            "table": "log_table",
            "row_ref": str(row_id or "")[:max_label_len],
        },
        "policy_notes": [
            "Synology Drive adapter opens SQLite databases read-only.",
            "File content, cookies, session tokens, credentials, and raw credential-bearing URLs remain forbidden.",
            "Drive Client sync-like activity is reported conservatively as drive_file_activity unless controlled validation proves a download/open action.",
        ],
    }
    if node:
        for key in [
            "permanent_id",
            "parent_permanent_id",
            "file_name",
            "folder_path",
            "display_path",
            "extension",
            "size_bytes",
            "file_type",
            "ctime",
            "mtime",
            "access_time",
        ]:
            if node.get(key) is not None:
                event[key] = node[key]
        event["correlation_refs"].append(
            {
                "type": "drive_view_node_db",
                "path": str(node.get("view_db")),
                "table": "node_table",
                "node_id": node.get("node_id"),
            }
        )
    return {key: value for key, value in event.items() if value not in (None, "", [])}


def read_drive_activity_events(sync_root: Path, limit: int, nas_host: str, max_label_len: int) -> dict[str, Any]:
    log_db = sync_root / "log-db.sqlite"
    if not log_db.is_file():
        return {
            "found": False,
            "stage": "drive_log_db_missing",
            "sync_root": str(sync_root),
            "events": [],
        }

    try:
        with _connect_ro(log_db) as conn:
            columns = [str(row["name"]) for row in conn.execute("PRAGMA table_info(log_table)").fetchall()]
            required = {"id", "type", "username", "view_id", "time", "p1", "client_type", "ip_address"}
            missing = sorted(required - set(columns))
            if missing:
                return {
                    "found": False,
                    "stage": "drive_log_schema_missing_columns",
                    "sync_root": str(sync_root),
                    "missing_columns": missing,
                    "events": [],
                }
            rows = [
                _row_to_dict(row) or {}
                for row in conn.execute(
                    "SELECT id, type, username, view_id, time, p1, p2, client_type, ip_address "
                    "FROM log_table WHERE length(p1) > 0 ORDER BY time DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]
    except sqlite3.Error as exc:
        return {
            "found": False,
            "stage": "drive_log_db_read_failed",
            "sync_root": str(sync_root),
            "error": str(exc),
            "events": [],
        }

    events = [_event_from_log_row(sync_root, row, nas_host, max_label_len) for row in rows]
    return {
        "found": True,
        "stage": "events_normalized",
        "sync_root": str(sync_root),
        "schema_summary": {
            "log_db": str(log_db),
            "log_table_columns": columns,
        },
        "events": events,
    }


def _run_remote(args: argparse.Namespace) -> dict[str, Any]:
    script_source = Path(__file__).read_text(encoding="utf-8")
    remote = f"{args.user}@{args.host}" if args.user else args.host
    ssh_command = [
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
        ssh_command.extend(["-o", f"IdentityFile={identity_file}", "-o", "IdentitiesOnly=yes"])
    ssh_command.extend(
        [
            remote,
            "sudo",
            "-n",
            "python3",
            "-",
            "--mode",
            "local",
            "--sync-root",
            args.sync_root,
            "--limit",
            str(args.limit),
            "--nas-host",
            args.nas_host,
            "--max-label-len",
            str(args.max_label_len),
        ]
    )
    proc = subprocess.run(
        ssh_command,
        input=script_source,
        text=True,
        capture_output=True,
        timeout=args.timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "found": False,
            "stage": "remote_drive_adapter_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[-1000:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "found": False,
            "stage": "remote_drive_adapter_invalid_json",
            "error": str(exc),
            "stdout_sample": proc.stdout[:1000],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--sync-root", default=DEFAULT_SYNC_ROOT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--nas-host", default="demo-nas")
    parser.add_argument("--max-label-len", type=int, default=120)
    parser.add_argument("--host", default="nas.example.local", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="", help="SSH user for --mode remote; empty uses ssh config or current user")
    parser.add_argument("--timeout-sec", type=int, default=30)
    args = parser.parse_args()

    if args.limit < 1:
        print(json.dumps({"found": False, "stage": "invalid_limit"}, indent=2, sort_keys=True))
        return 2

    if args.mode == "remote":
        result = _run_remote(args)
    else:
        result = read_drive_activity_events(Path(args.sync_root), args.limit, args.nas_host, args.max_label_len)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
