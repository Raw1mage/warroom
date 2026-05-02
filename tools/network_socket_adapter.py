#!/usr/bin/env python3
"""Collect bounded NAS socket/listening-port metadata as Warroom events."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any


TCP_STATES = {
    "01": "established",
    "02": "syn_sent",
    "03": "syn_recv",
    "04": "fin_wait1",
    "05": "fin_wait2",
    "06": "time_wait",
    "07": "close",
    "08": "close_wait",
    "09": "last_ack",
    "0A": "listen",
    "0B": "closing",
}


def _hex_ipv4(value: str) -> str:
    raw = bytes.fromhex(value)
    return socket.inet_ntop(socket.AF_INET, raw[::-1])


def _hex_ipv6(value: str) -> str:
    raw = bytes.fromhex(value)
    chunks = [raw[index : index + 4][::-1] for index in range(0, 16, 4)]
    return socket.inet_ntop(socket.AF_INET6, b"".join(chunks))


def _parse_addr_port(value: str, ipv6: bool) -> tuple[str, int]:
    addr_hex, port_hex = value.split(":", 1)
    address = _hex_ipv6(addr_hex) if ipv6 else _hex_ipv4(addr_hex)
    return address, int(port_hex, 16)


def _read_tcp_table(path: Path, ipv6: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]
    except OSError:
        return rows
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            local_ip, local_port = _parse_addr_port(parts[1], ipv6)
            remote_ip, remote_port = _parse_addr_port(parts[2], ipv6)
        except (OSError, ValueError):
            continue
        state = TCP_STATES.get(parts[3].upper(), parts[3].lower())
        rows.append(
            {
                "protocol": "tcp6" if ipv6 else "tcp4",
                "local_ip": local_ip,
                "local_port": local_port,
                "remote_ip": remote_ip,
                "remote_port": remote_port,
                "state": state,
            }
        )
    return rows


def collect_socket_snapshot(nas_host: str, top_limit: int) -> dict[str, Any]:
    observed_at = int(time.time())
    rows = _read_tcp_table(Path("/proc/net/tcp"), False) + _read_tcp_table(Path("/proc/net/tcp6"), True)
    state_counts = Counter(str(row["state"]) for row in rows)
    remote_ips = Counter(str(row["remote_ip"]) for row in rows if row.get("remote_ip") not in {"0.0.0.0", "::"})
    listening_ports = sorted({int(row["local_port"]) for row in rows if row.get("state") == "listen"})
    top_remote_ips = [
        {"source_ip": ip, "connection_count": count}
        for ip, count in remote_ips.most_common(max(1, top_limit))
    ]
    event: dict[str, Any] = {
        "event_id": f"network-socket-{nas_host}-{observed_at}",
        "action": "network_socket_snapshot",
        "nas_host": nas_host,
        "source_channel": "network_socket",
        "source_app": "nas_network",
        "source_surface": "ssh_transient_payload",
        "confidence": 0.9,
        "observed_at": observed_at,
        "tcp_connection_count": len(rows),
        "tcp_established_count": state_counts.get("established", 0),
        "tcp_listen_count": state_counts.get("listen", 0),
        "tcp_remote_ip_count": len(remote_ips),
        "tcp_state_counts": dict(sorted(state_counts.items())),
        "listening_ports": listening_ports[: max(1, top_limit)],
        "top_remote_ips": top_remote_ips,
        "policy_notes": [
            "Network socket adapter reads kernel socket metadata only.",
            "Top remote IPs are bounded to avoid high-cardinality labels.",
        ],
    }
    return {"found": True, "stage": "network_socket_snapshot", "events": [event]}


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
    command.extend([remote, "sudo", "-n", "python3", "-", "--mode", "local", "--nas-host", args.nas_host, "--top-limit", str(args.top_limit)])
    proc = subprocess.run(command, input=script_source, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
    if proc.returncode != 0:
        return {"found": False, "stage": "remote_network_socket_adapter_failed", "returncode": proc.returncode, "stderr": proc.stderr.strip()[-1000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"found": False, "stage": "remote_network_socket_adapter_invalid_json", "error": str(exc), "stdout_sample": proc.stdout[:1000]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--nas-host", default="rawdb")
    parser.add_argument("--host", default="rawdb", help="SSH host alias or address for --mode remote")
    parser.add_argument("--user", default="", help="SSH user for --mode remote; empty uses ssh config or current user")
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--top-limit", type=int, default=10)
    args = parser.parse_args()
    if args.top_limit < 1:
        print(json.dumps({"found": False, "stage": "invalid_top_limit"}, indent=2, sort_keys=True))
        return 2
    result = _run_remote(args) if args.mode == "remote" else collect_socket_snapshot(args.nas_host, args.top_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
