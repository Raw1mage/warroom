#!/usr/bin/env python3
"""Collect local Warroom DLP event JSON files and optionally push them to Loki."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ["event_id", "action", "source_channel", "source_app", "confidence"]
LABEL_KEYS = ["source_channel", "source_app", "action", "nas_host"]
LABEL_VALUE_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


class CollectorError(Exception):
    def __init__(self, stage: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.details = details


def _fail(stage: str, message: str, **details: Any) -> None:
    raise CollectorError(stage, message, **details)


def _error_payload(exc: CollectorError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "stage": exc.stage,
        "error": exc.message,
    }
    payload.update(exc.details)
    return payload


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        _fail("input_missing", "event file does not exist", path=str(path))
    if not path.is_file():
        _fail("input_not_file", "event path is not a file", path=str(path))

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail("invalid_json", "event file is not valid JSON", path=str(path), detail=str(exc))

    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        events: list[dict[str, Any]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                _fail("invalid_event", "JSON array item is not an object", path=str(path), index=index)
            events.append(item)
        return events

    _fail("invalid_payload", "event file must contain a JSON object or array", path=str(path))


def _source_channel_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "unknown"
        return str(value[0])
    return str(value)


def _bounded_label(value: Any) -> str:
    text = _source_channel_value(value).strip()
    if not text:
        text = "unknown"
    return LABEL_VALUE_RE.sub("_", text)[:80]


def _validate_event(event: dict[str, Any], input_path: Path, index: int) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in event or event[field] in (None, "")]
    if missing:
        _fail("missing_required_fields", "event is missing required fields", path=str(input_path), index=index, missing=missing)

    confidence = event["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        _fail("invalid_confidence", "confidence must be a number", path=str(input_path), index=index)
    if confidence < 0 or confidence > 1:
        _fail("invalid_confidence", "confidence must be between 0.0 and 1.0", path=str(input_path), index=index)

    normalized = dict(event)
    normalized.setdefault("ingested_at", int(time.time()))
    normalized["collector"] = "warroom-dlp-event-collector"
    return normalized


def load_events(paths: list[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        for index, event in enumerate(_load_json_file(path)):
            events.append(_validate_event(event, path, index))
    return events


def _labels_for_event(event: dict[str, Any]) -> dict[str, str]:
    labels = {"job": "warroom-dlp-event-collector"}
    for key in LABEL_KEYS:
        if key in event and event[key] not in (None, ""):
            labels[key] = _bounded_label(event[key])
    return labels


def _loki_payload(events: list[dict[str, Any]]) -> dict[str, Any]:
    streams: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
    for event in events:
        labels = _labels_for_event(event)
        key = tuple(sorted(labels.items()))
        if key not in streams:
            streams[key] = {"stream": labels, "values": []}
        streams[key]["values"].append([str(time.time_ns()), json.dumps(event, ensure_ascii=False, separators=(",", ":"))])
    return {"streams": list(streams.values())}


def push_loki(loki_url: str, events: list[dict[str, Any]], timeout_sec: int) -> None:
    payload = _loki_payload(events)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        loki_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            response.read()
            if response.status >= 300:
                _fail("loki_push_failed", "Loki push returned non-success status", status=response.status)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _fail("loki_push_failed", "failed to push events to Loki", detail=str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print normalized JSON lines and do not push to Loki")
    parser.add_argument("--loki-url", default=None, help="Loki push API URL")
    parser.add_argument("--timeout-sec", type=int, default=5)
    parser.add_argument("event_files", nargs="+", help="JSON event object or JSON array files")
    args = parser.parse_args()

    try:
        if args.timeout_sec < 1:
            _fail("invalid_timeout", "timeout must be at least 1 second")
        events = load_events([Path(item) for item in args.event_files])
        if args.dry_run:
            for event in events:
                print(json.dumps(event, ensure_ascii=False, sort_keys=True))
            return 0
        if not args.loki_url:
            _fail("loki_url_required", "--loki-url is required unless --dry-run is set")
        push_loki(args.loki_url, events, args.timeout_sec)
        print(json.dumps({"ok": True, "events_pushed": len(events)}, sort_keys=True))
        return 0
    except CollectorError as exc:
        print(json.dumps(_error_payload(exc), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
