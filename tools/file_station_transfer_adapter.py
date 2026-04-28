#!/usr/bin/env python3
"""Read Synology File Station transfer DB rows as Warroom DLP events.

Read-only helper for `/volume1/@database/synolog/.DSMFMXFERDB`. It never
reads file contents and never installs code on the NAS when used through SSH.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = "/volume1/@database/synolog/.DSMFMXFERDB"
TRANSFER_HINT_COLUMNS = {
    "time",
    "timestamp",
    "date",
    "ip",
    "username",
    "user",
    "cmd",
    "command",
    "action",
    "filename",
    "file",
    "path",
    "filesize",
    "size",
}
TEXT_ACTION_COLUMNS = ["cmd", "command", "action", "type", "operation"]
TIME_COLUMNS = ["time", "timestamp", "date", "created_at", "start_time"]
ACTOR_COLUMNS = ["username", "user", "account", "owner"]
IP_COLUMNS = ["ip", "source_ip", "client_ip", "remote_ip"]
PATH_COLUMNS = ["filename", "file", "path", "filepath", "name"]
SIZE_COLUMNS = ["filesize", "size", "file_size", "bytes"]
ID_COLUMNS = ["id", "log_id", "taskid", "task_id"]


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _discover_db_files(db_path: Path) -> list[Path]:
    if db_path.is_file():
        return [db_path]
    if not db_path.exists():
        return []
    if not db_path.is_dir():
        return []

    candidates: list[Path] = []
    for child in sorted(db_path.iterdir()):
        if child.is_file() and not child.name.endswith(("-wal", "-shm", "-journal")):
            candidates.append(child)
    return candidates


def _discover_schema(db_file: Path) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    try:
        with _connect_ro(db_file) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            for row in rows:
                table_name = str(row["name"])
                columns = [
                    str(col["name"])
                    for col in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
                ]
                matching = sorted(set(columns) & TRANSFER_HINT_COLUMNS)
                tables.append(
                    {
                        "table": table_name,
                        "columns": columns,
                        "transfer_hint_columns": matching,
                        "candidate_score": len(matching),
                    }
                )
    except sqlite3.Error as exc:
        return {
            "db_file": str(db_file),
            "readable": False,
            "error": str(exc),
            "tables": [],
        }

    return {
        "db_file": str(db_file),
        "readable": True,
        "tables": tables,
    }


def discover_transfer_schema(db_path: Path) -> dict[str, Any]:
    db_files = _discover_db_files(db_path)
    if not db_files:
        return {
            "found": False,
            "stage": "transfer_db_missing",
            "db_path": str(db_path),
            "schemas": [],
        }

    schemas = [_discover_schema(db_file) for db_file in db_files]
    candidate_tables = []
    for schema in schemas:
        for table in schema.get("tables", []):
            columns = set(table["columns"])
            has_action = bool(columns & set(TEXT_ACTION_COLUMNS))
            has_path = bool(columns & set(PATH_COLUMNS))
            if has_action and has_path:
                candidate_tables.append(
                    {
                        "db_file": schema["db_file"],
                        "table": table["table"],
                        "candidate_score": table["candidate_score"],
                        "columns": table["columns"],
                    }
                )

    return {
        "found": bool(candidate_tables),
        "stage": "schema_discovered" if candidate_tables else "candidate_table_not_found",
        "db_path": str(db_path),
        "schemas": schemas,
        "candidate_tables": sorted(candidate_tables, key=lambda item: item["candidate_score"], reverse=True),
    }


def _classify_action(command_value: Any) -> tuple[str, float, str]:
    text = str(command_value or "").strip().lower()
    if not text:
        return "unknown", 0.35, "missing_command"
    if "download" in text or text in {"get", "dl"}:
        return "webapp_file_download", 0.92, "explicit_download_command"
    if "export" in text or "compress" in text or "archive" in text or "zip" in text:
        return "webapp_file_export", 0.88, "explicit_export_like_command"
    return "unknown", 0.45, "unmapped_command"


def _normalize_path(path_value: Any) -> tuple[str | None, str | None, str | None]:
    if path_value in (None, ""):
        return None, None, None
    display_path = str(path_value)
    file_name = os.path.basename(display_path.rstrip("/")) or None
    folder_path = os.path.dirname(display_path) or None
    return display_path, file_name, folder_path


def _event_from_row(
    *,
    row: dict[str, Any],
    db_file: Path,
    table: str,
    row_number: int,
    nas_host: str,
    max_label_len: int,
) -> dict[str, Any]:
    command_value = _first_present(row, TEXT_ACTION_COLUMNS)
    action, confidence, action_reason = _classify_action(command_value)
    path_value = _first_present(row, PATH_COLUMNS)
    display_path, file_name, folder_path = _normalize_path(path_value)
    row_id = _first_present(row, ID_COLUMNS) or row_number
    size_value = _first_present(row, SIZE_COLUMNS)

    event: dict[str, Any] = {
        "event_id": f"file-station-transfer-{table}-{row_id}",
        "action": action,
        "nas_host": nas_host,
        "source_channel": "file_station_transfer_db",
        "source_app": "file_station",
        "source_surface": "transfer_db",
        "object_type": "file" if display_path else "unknown",
        "protocol": "synology_file_station_web",
        "confidence": confidence,
        "observed_at": _first_present(row, TIME_COLUMNS),
        "actor": _first_present(row, ACTOR_COLUMNS),
        "source_ip": _first_present(row, IP_COLUMNS),
        "file_name": file_name,
        "folder_path": folder_path,
        "display_path": display_path,
        "extension": os.path.splitext(file_name or "")[1].lower() if file_name else None,
        "size_bytes": int(size_value) if isinstance(size_value, int) or str(size_value or "").isdigit() else None,
        "correlation_refs": [
            {
                "type": "file_station_transfer_db",
                "path": str(db_file),
                "table": table,
                "row_ref": str(row_id)[:max_label_len],
                "action_reason": action_reason,
            }
        ],
        "raw_ref": {
            "type": "sqlite_row_ref",
            "path": str(db_file),
            "table": table,
            "row_ref": str(row_id)[:max_label_len],
        },
        "policy_notes": [
            "File Station adapter opens SQLite databases read-only.",
            "File content, cookies, session tokens, credentials, and raw credential-bearing URLs remain forbidden.",
        ],
    }

    return {key: value for key, value in event.items() if value is not None}


def read_transfer_events(db_path: Path, limit: int, nas_host: str, max_label_len: int) -> dict[str, Any]:
    schema = discover_transfer_schema(db_path)
    if not schema.get("found"):
        schema["events"] = []
        return schema

    events: list[dict[str, Any]] = []
    for candidate in schema["candidate_tables"]:
        db_file = Path(candidate["db_file"])
        table = candidate["table"]
        columns = candidate["columns"]
        select_columns = [
            column
            for column in columns
            if column in set(TEXT_ACTION_COLUMNS + TIME_COLUMNS + ACTOR_COLUMNS + IP_COLUMNS + PATH_COLUMNS + SIZE_COLUMNS + ID_COLUMNS)
        ]
        if not select_columns:
            continue

        with _connect_ro(db_file) as conn:
            order_column = next((column for column in TIME_COLUMNS + ID_COLUMNS if column in columns), None)
            order_clause = f" ORDER BY {_quote_identifier(order_column)} DESC" if order_column else ""
            query = (
                "SELECT "
                + ", ".join(_quote_identifier(column) for column in select_columns)
                + f" FROM {_quote_identifier(table)}"
                + order_clause
                + " LIMIT ?"
            )
            for row_number, row in enumerate(conn.execute(query, (limit,)).fetchall(), start=1):
                event = _event_from_row(
                    row=_row_to_dict(row) or {},
                    db_file=db_file,
                    table=table,
                    row_number=row_number,
                    nas_host=nas_host,
                    max_label_len=max_label_len,
                )
                events.append(event)
                if len(events) >= limit:
                    break
        if len(events) >= limit:
            break

    return {
        "found": True,
        "stage": "events_normalized",
        "db_path": str(db_path),
        "schema_summary": [
            {
                "db_file": item["db_file"],
                "table": item["table"],
                "columns": item["columns"],
            }
            for item in schema["candidate_tables"]
        ],
        "events": events,
    }


def _run_remote(args: argparse.Namespace) -> dict[str, Any]:
    script_source = Path(__file__).read_text(encoding="utf-8")
    remote = f"{args.user}@{args.host}"
    proc = subprocess.run(
        [
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
            "--db-path",
            args.db_path,
            "--limit",
            str(args.limit),
            "--nas-host",
            args.nas_host,
            "--max-label-len",
            str(args.max_label_len),
        ],
        input=script_source,
        text=True,
        capture_output=True,
        timeout=args.timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "found": False,
            "stage": "remote_transfer_adapter_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[-1000:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "found": False,
            "stage": "remote_transfer_adapter_invalid_json",
            "error": str(exc),
            "stdout_sample": proc.stdout[:1000],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--nas-host", default="demo-nas")
    parser.add_argument("--max-label-len", type=int, default=120)
    parser.add_argument("--host", default="nas.example.local", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="nas-admin", help="SSH user for --mode remote")
    parser.add_argument("--timeout-sec", type=int, default=30)
    args = parser.parse_args()

    if args.limit < 1:
        print(json.dumps({"found": False, "stage": "invalid_limit"}, indent=2, sort_keys=True))
        return 2

    if args.mode == "remote":
        result = _run_remote(args)
    else:
        result = read_transfer_events(Path(args.db_path), args.limit, args.nas_host, args.max_label_len)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
