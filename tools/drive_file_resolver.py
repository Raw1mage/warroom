#!/usr/bin/env python3
"""Resolve Synology Drive permanent_id/file_id to readable metadata.

Read-only helper for Warroom DLP enrichment. It does not read file contents.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def resolve_drive_file(sync_root: Path, permanent_id: int) -> dict[str, Any]:
    route_db = sync_root / "view-route-db.sqlite"
    if not route_db.exists():
        return {
            "found": False,
            "stage": "route_db_missing",
            "route_db": str(route_db),
        }

    with _connect_ro(route_db) as route_conn:
        route = _row_to_dict(
            route_conn.execute(
                "SELECT permanent_id, view_id, length(permanent_link) AS permanent_link_len "
                "FROM route_table WHERE permanent_id = ?",
                (permanent_id,),
            ).fetchone()
        )

    if route is None:
        return {
            "found": False,
            "stage": "route_not_found",
            "permanent_id": permanent_id,
        }

    view_id = int(route["view_id"])
    view_db = sync_root / "view" / str(view_id) / "view-db.sqlite"
    if not view_db.exists():
        return {
            "found": False,
            "stage": "view_db_missing",
            "permanent_id": permanent_id,
            "view_id": view_id,
            "view_db": str(view_db),
        }

    with _connect_ro(view_db) as view_conn:
        node = _row_to_dict(
            view_conn.execute(
                "SELECT node_id, parent_id, file_type, name, extension, v_file_size, "
                "permanent_id, parent_permanent_id, ctime, mtime, access_time "
                "FROM node_table WHERE permanent_id = ?",
                (permanent_id,),
            ).fetchone()
        )
        if node is None:
            return {
                "found": False,
                "stage": "node_not_found",
                "permanent_id": permanent_id,
                "view_id": view_id,
            }

        chain = []
        current = node
        seen_node_ids = set()
        while current is not None:
            node_id = current.get("node_id")
            if node_id in seen_node_ids:
                break
            seen_node_ids.add(node_id)
            chain.append(current)
            parent_id = current.get("parent_id")
            if parent_id in (None, 0):
                break
            current = _row_to_dict(
                view_conn.execute(
                    "SELECT node_id, parent_id, file_type, name, extension, v_file_size, "
                    "permanent_id, parent_permanent_id, ctime, mtime, access_time "
                    "FROM node_table WHERE node_id = ?",
                    (parent_id,),
                ).fetchone()
            )

    ordered_chain = list(reversed(chain))
    path_parts = [item["name"] for item in ordered_chain if item.get("name")]
    display_path = "/" + "/".join(path_parts)
    folder_path = "/" + "/".join(path_parts[:-1]) if len(path_parts) > 1 else "/"

    return {
        "found": True,
        "source": "synology_drive_db",
        "permanent_id": permanent_id,
        "view_id": view_id,
        "node_id": node["node_id"],
        "parent_id": node["parent_id"],
        "file_type": node["file_type"],
        "file_name": node["name"],
        "folder_path": folder_path,
        "display_path": display_path,
        "extension": node["extension"] or os.path.splitext(str(node["name"]))[1].lower(),
        "size_bytes": node["v_file_size"],
        "ctime": node["ctime"],
        "mtime": node["mtime"],
        "access_time": node["access_time"],
        "parent_permanent_id": node["parent_permanent_id"],
        "route": route,
        "chain": [
            {
                "node_id": item["node_id"],
                "parent_id": item["parent_id"],
                "file_type": item["file_type"],
                "name": item["name"],
                "permanent_id": item["permanent_id"],
            }
            for item in ordered_chain
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("permanent_id", type=int, help="Synology Drive permanent_id/file_id")
    parser.add_argument(
        "--sync-root",
        default="/volume1/@synologydrive/@sync",
        help="Path containing view-route-db.sqlite and view/<id>/view-db.sqlite",
    )
    args = parser.parse_args()

    result = resolve_drive_file(Path(args.sync_root), args.permanent_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
