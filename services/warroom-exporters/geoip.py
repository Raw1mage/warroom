"""
Warroom: GeoIP + ASN enrichment service.

Two HTTP endpoints:
  GET /lookup?ip=X.Y.Z.W   -> JSON {country_iso, country_name, asn_number, asn_org}
  GET /metrics             -> Prometheus exposition format

The /metrics endpoint additionally emits per-IP labels for any IPs the
service has seen via /lookup or via the upstream-IP feed mode, so dashboards
can join attacker tables with country/asn dimensions without doing the
lookup in the dashboard.

Data sources (from refs/ip-location-db submodule):
  - dbip-country-mmdb (CC-BY 4.0, db-ip.com)
  - asn-mmdb (CC-BY-SA, iptoasn.com)

Env:
  LISTEN_PORT       default 9118
  CITY_DB_PATH      default /data/dbip-city-mmdb/dbip-city-ipv4.mmdb
  ASN_DB_PATH       default /data/asn.mmdb
  IP_FEED_URL       optional Loki query URL to harvest IPs every cycle
  IP_FEED_QUERY     optional LogQL query (defaults to asusrouter WSLSSH attackers)
  IP_FEED_INTERVAL  default 60
"""
import json
import os
import re
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer

import maxminddb

LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9118"))
CITY_DB = os.environ.get("CITY_DB_PATH", "/data/dbip-city-mmdb/dbip-city-ipv4.mmdb")
ASN_DB = os.environ.get("ASN_DB_PATH", "/data/asn-mmdb/asn.mmdb")
IP_FEED_URL = os.environ.get("IP_FEED_URL", "")
IP_FEED_INTERVAL = int(os.environ.get("IP_FEED_INTERVAL", "60"))

# Per-channel queries. Each channel contributes to per-IP channel-hit tracking
# so the exporter can emit `warroom_attacker_channels{ip=...}` for cross-channel
# correlation alerting.
IP_FEED_CHANNELS = [
    ("ssh",   'topk(200, sum by (src_ip) (count_over_time({job="asus-router", prog="kernel"} '
              '|= `WSLSSH-` | regexp `SRC=(?P<src_ip>[\\d.]+)` [24h])))'),
    ("nginx", 'topk(200, sum by (client_ip) (count_over_time({job="rawdb-nginx"} '
              '| regexp `client: (?P<client_ip>[\\d.]+)` [24h])))'),
    ("mail",  'topk(200, sum by (client_ip) (count_over_time({job="rawdb-mail"} '
              '| regexp `(?:from \\[|rip=)(?P<client_ip>[\\d.]+)` [24h])))'),
]

# {ip: set(channel_name, ...)} populated by the feeder, read by render_metrics
_channel_hits: "dict[str, set[str]]" = {}
_channel_hits_lock = threading.Lock()

# 16 KB LRU per DB is plenty for the volumes we see (~hundreds of unique IPs/day)
_cache: "OrderedDict[str, dict]" = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 16384

_city_reader = None
_asn_reader = None


def _init_dbs():
    global _city_reader, _asn_reader
    _city_reader = maxminddb.open_database(CITY_DB)
    _asn_reader = maxminddb.open_database(ASN_DB)


_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _is_routable(ip):
    if not _IP_RE.match(ip):
        return False
    parts = [int(x) for x in ip.split(".")]
    a, b = parts[0], parts[1]
    # quick RFC1918 + loopback + link-local + CGNAT screen — no enrichment for these
    if a in (10, 127):
        return False
    if a == 192 and b == 168:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 169 and b == 254:
        return False
    if a == 100 and 64 <= b <= 127:
        return False
    return True


def lookup(ip):
    if not _is_routable(ip):
        return {"ip": ip, "country_iso": "", "country_name": "", "asn_number": 0, "asn_org": "", "private": True}

    with _cache_lock:
        cached = _cache.get(ip)
        if cached is not None:
            _cache.move_to_end(ip)
            return cached

    out = {
        "ip": ip, "country_iso": "", "city": "", "state": "",
        "latitude": 0.0, "longitude": 0.0,
        "asn_number": 0, "asn_org": "", "private": False,
    }
    try:
        # dbip-city schema: {country_code, city, state1, state2, latitude, longitude, ...}
        c = _city_reader.get(ip) or {}
        out["country_iso"] = c.get("country_code", "") or ""
        out["city"] = c.get("city", "") or ""
        out["state"] = c.get("state1", "") or ""
        out["latitude"] = float(c.get("latitude") or 0.0)
        out["longitude"] = float(c.get("longitude") or 0.0)
    except Exception:
        pass
    try:
        # iptoasn schema: {autonomous_system_number, autonomous_system_organization}
        a = _asn_reader.get(ip) or {}
        out["asn_number"] = int(a.get("autonomous_system_number") or 0)
        out["asn_org"] = a.get("autonomous_system_organization", "") or ""
    except Exception:
        pass

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.popitem(last=False)
        _cache[ip] = out
    return out


def _esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def render_metrics():
    lines = []
    add = lines.append
    add("# HELP warroom_geoip_lookups_total Total lookups served.")
    add("# TYPE warroom_geoip_lookups_total counter")
    add(f"warroom_geoip_lookups_total {LOOKUP_COUNT[0]}")
    add("# HELP warroom_geoip_cache_size Current LRU cache size.")
    add("# TYPE warroom_geoip_cache_size gauge")
    with _cache_lock:
        add(f"warroom_geoip_cache_size {len(_cache)}")
        ips = list(_cache.items())
    add("# HELP warroom_ip_info Country/City/ASN labels for IPs seen by the enricher (gauge=1).")
    add("# TYPE warroom_ip_info gauge")
    for ip, info in ips:
        if info.get("private"):
            continue
        add(
            f'warroom_ip_info{{ip="{_esc(ip)}",country_iso="{_esc(info["country_iso"])}",'
            f'city="{_esc(info["city"])}",state="{_esc(info["state"])}",'
            f'asn_number="{info["asn_number"]}",asn_org="{_esc(info["asn_org"])}"}} 1'
        )

    # Per-IP cross-channel hit count (number of distinct attack channels
    # this IP appeared in during the most recent feeder cycle).
    with _channel_hits_lock:
        snapshot = {ip: sorted(chans) for ip, chans in _channel_hits.items()}
    add("# HELP warroom_attacker_channels Distinct attack channels this IP hit in last feeder cycle.")
    add("# TYPE warroom_attacker_channels gauge")
    for ip, chans in snapshot.items():
        add(f'warroom_attacker_channels{{ip="{_esc(ip)}",channels="{_esc(",".join(chans))}"}} {len(chans)}')

    return "\n".join(lines) + "\n"


LOOKUP_COUNT = [0]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/lookup"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            ip = (qs.get("ip") or [""])[0]
            if not ip:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"missing ip"}')
                return
            LOOKUP_COUNT[0] += 1
            body = json.dumps(lookup(ip)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/metrics":
            body = render_metrics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


def feeder_loop():
    """Background harvester that pre-warms cache with IPs from Loki queries
    AND tracks per-IP channel-hit set for cross-channel correlation."""
    if not IP_FEED_URL:
        return
    import urllib.parse
    import urllib.request
    while True:
        cycle: "dict[str, set[str]]" = {}
        total = 0
        for chan_name, q in IP_FEED_CHANNELS:
            try:
                url = IP_FEED_URL + "?" + urllib.parse.urlencode({"query": q})
                body = urllib.request.urlopen(url, timeout=10).read()
                data = json.loads(body)
                for row in data.get("data", {}).get("result", []):
                    metric = row.get("metric") or {}
                    ip = metric.get("src_ip") or metric.get("client_ip") or metric.get("remote_addr") or ""
                    if not ip or ip == "null":
                        continue
                    lookup(ip)
                    cycle.setdefault(ip, set()).add(chan_name)
                    total += 1
            except Exception as e:
                print(f"[feed] error on channel {chan_name}: {e.__class__.__name__}: {e}", flush=True)
        with _channel_hits_lock:
            _channel_hits.clear()
            _channel_hits.update(cycle)
        print(f"[feed] warmed {total} ip-channel pairs, distinct ips={len(cycle)}, multi-channel={sum(1 for s in cycle.values() if len(s) >= 2)}", flush=True)
        time.sleep(IP_FEED_INTERVAL)


if __name__ == "__main__":
    _init_dbs()
    print(f"warroom-geoip-enrich listening :{LISTEN_PORT}", flush=True)
    print(f"  city_db    = {CITY_DB}", flush=True)
    print(f"  asn_db     = {ASN_DB}", flush=True)
    if IP_FEED_URL:
        threading.Thread(target=feeder_loop, daemon=True).start()
    HTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
