"""
DLP insider baseline statistical report.

Queries Loki for the last 7 days and prints a markdown summary of:
  - Per-user activity volume (nas_home_log via display_path, file_station, auth_log)
  - Hour-of-day distribution (working hours / late-night / weekend ratio)
  - Download size distribution
  - Login source IPs
  - Top folders per user
  - Outlier preview

Intent: inform threshold design before deploying alert rules; *do not* alert.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta

LOKI = "http://localhost:3100"
WINDOW_DAYS = 7
NOW = int(time.time())
START = NOW - WINDOW_DAYS * 86400
TPE = timezone(timedelta(hours=8))
JSON_OUT = "/home/pkcs12/projects/warroom/services/warroom-rawdb-nginx-tail/state/dlp-baseline-snapshot.json"


def lq_instant(query):
    url = f"{LOKI}/loki/api/v1/query?" + urllib.parse.urlencode({"query": query, "time": NOW})
    try:
        body = urllib.request.urlopen(url, timeout=60).read()
        return json.loads(body).get("data", {}).get("result", [])
    except Exception as e:
        print(f"# WARN: {e}", file=sys.stderr)
        return []


def lq_range_lines(query, limit=2000):
    url = f"{LOKI}/loki/api/v1/query_range?" + urllib.parse.urlencode({
        "query": query, "start": f"{START}000000000", "end": f"{NOW}000000000", "limit": str(limit),
    })
    rows = []
    try:
        body = urllib.request.urlopen(url, timeout=60).read()
        data = json.loads(body)
        for stream in data.get("data", {}).get("result", []):
            for ts_ns, line in (stream.get("values") or []):
                rows.append((int(ts_ns), line, stream.get("stream") or {}))
    except Exception as e:
        print(f"# WARN: {e}", file=sys.stderr)
    return rows


def pct(arr, p):
    if not arr: return 0
    arr = sorted(arr)
    return arr[max(0, min(len(arr)-1, int(p/100.0*(len(arr)-1))))]


def fmt(n):
    n = float(n)
    for u in ['B','KB','MB','GB']:
        if n < 1024: return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


snapshot = {"window_days": WINDOW_DAYS, "generated_at": NOW, "users": {}}

print(f"# DLP Insider Baseline Report — last {WINDOW_DAYS}d (Asia/Taipei)")
print(f"_Generated {datetime.now(TPE).isoformat(timespec='seconds')}_\n")

# ===== 1. Identity sources =====
print("## 1. Identity coverage (where do we see real users?)\n")
print("| Channel | Identity field | Approach |")
print("|---|---|---|")
print("| `nas_home_log` | `display_path` → `/homes/<user>/` | regex extract |")
print("| `file_station_transfer_db` | `actor` JSON field | direct |")
print("| `auth_log` | `actor` JSON field | direct (root/wuyangadmin/AIConsole/…) |")
print()

# ===== 2. Per-user volume (NAS home folder activity) =====
print("## 2. NAS home-folder activity (per user, 7d)\n")
res = lq_instant('sum by (home_user) (count_over_time({source_channel="nas_home_log"} | json | regexp `/homes/(?P<home_user>[A-Za-z0-9_-]+)` [%dd]))' % WINDOW_DAYS)
home_totals = {r["metric"]["home_user"]: int(float(r["value"][1])) for r in res if r.get("metric", {}).get("home_user")}
if home_totals:
    print("| User home | Events 7d | Daily avg | Events/hour avg |")
    print("|---|---:|---:|---:|")
    for user, total in sorted(home_totals.items(), key=lambda x: -x[1]):
        d_avg = total / WINDOW_DAYS
        h_avg = d_avg / 24
        print(f"| `{user}` | {total:,} | {d_avg:,.0f} | {h_avg:,.0f} |")
        snapshot["users"].setdefault(user, {})["home_events_7d"] = total
print()

# ===== 3. Hour-of-day distribution per user =====
print("## 3. Hour-of-day distribution (business vs late-night vs weekend)\n")
samples = lq_range_lines('{source_channel="nas_home_log"}', limit=5000)
hour_buckets = defaultdict(lambda: defaultdict(int))
wkday_buckets = defaultdict(lambda: defaultdict(int))
for ts_ns, line, _ in samples:
    try:
        rec = json.loads(line)
        path = rec.get("display_path", "")
    except Exception:
        continue
    if "/homes/" not in path:
        continue
    user = path.split("/homes/", 1)[1].split("/", 1)[0].rstrip(")\"'")
    if not user: continue
    dt = datetime.fromtimestamp(ts_ns/1e9, TPE)
    hour_buckets[user][dt.hour] += 1
    wkday_buckets[user][dt.weekday()] += 1  # Mon=0 .. Sun=6

if hour_buckets:
    print(f"Sample size: {sum(sum(b.values()) for b in hour_buckets.values()):,} lines, {len(hour_buckets)} users\n")
    print("| User | 9–18 (work) | 0–6 (late-night) | 22–24 (after-hours) | Weekend | Peak hour |")
    print("|---|---:|---:|---:|---:|---:|")
    for user, buckets in sorted(hour_buckets.items(), key=lambda x: -sum(x[1].values())):
        total = sum(buckets.values())
        if total < 10:
            continue
        bh = sum(buckets[h] for h in range(9,19))
        ln = sum(buckets[h] for h in range(0,7))
        ah = sum(buckets[h] for h in range(22,24))
        we = sum(wkday_buckets[user][d] for d in (5,6))
        peak_h = max(buckets, key=lambda h: buckets[h])
        s = snapshot["users"].setdefault(user, {})
        s["business_hours_pct"] = round(bh*100/total, 1)
        s["late_night_pct"] = round(ln*100/total, 1)
        s["weekend_pct"] = round(we*100/total, 1)
        s["peak_hour"] = peak_h
        s["hourly_p95"] = pct([buckets[h] for h in range(24)], 95)
        print(f"| `{user}` | {bh*100/total:.0f}% | {ln*100/total:.0f}% | {ah*100/total:.0f}% | {we*100/total:.0f}% | {peak_h:02d}:00 |")
print()

# ===== 4. file_station_transfer_db downloads =====
print("## 4. File Station webapp transfer activity (per actor, 7d)\n")
res = lq_instant('sum by (actor, action) (count_over_time({source_channel="file_station_transfer_db"} | json [%dd]))' % WINDOW_DAYS)
ft_user_action = defaultdict(lambda: defaultdict(int))
for r in res:
    a = r.get("metric", {}).get("actor", "")
    act = r.get("metric", {}).get("action", "")
    if a:
        ft_user_action[a][act] = int(float(r["value"][1]))

if ft_user_action:
    print("| Actor | webapp_file_download | other actions |")
    print("|---|---:|---:|")
    for actor, acts in sorted(ft_user_action.items(), key=lambda x: -sum(x[1].values())):
        dl = acts.get("webapp_file_download", 0)
        other = sum(acts.values()) - dl
        print(f"| `{actor}` | {dl} | {other} |")
        snapshot["users"].setdefault(actor, {})["fs_download_count_7d"] = dl

# ===== 5. Download size per actor =====
print("\n## 5. webapp_file_download size distribution per actor (7d)\n")
samples = lq_range_lines('{source_channel="file_station_transfer_db", action="webapp_file_download"}', limit=2000)
sizes_by = defaultdict(list)
for _, line, _ in samples:
    try:
        rec = json.loads(line)
        s = int(rec.get("size_bytes") or 0)
        a = rec.get("actor") or ""
        if a and s > 0:
            sizes_by[a].append(s)
    except Exception:
        pass
if sizes_by:
    print("| Actor | # downloads | Total bytes | P50 | P95 | Max | Anomaly threshold (5× P95) |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for actor, sizes in sorted(sizes_by.items(), key=lambda x: -sum(x[1])):
        p50, p95, mx = pct(sizes,50), pct(sizes,95), max(sizes)
        thresh = p95 * 5
        snapshot["users"].setdefault(actor, {})["dl_p95_bytes"] = p95
        snapshot["users"][actor]["dl_proposed_threshold_5x_p95"] = thresh
        print(f"| `{actor}` | {len(sizes)} | {fmt(sum(sizes))} | {fmt(p50)} | {fmt(p95)} | {fmt(mx)} | {fmt(thresh)} |")

# ===== 6. auth_log login activity =====
print("\n## 6. Auth-log per actor (last 7d)\n")
res = lq_instant('sum by (actor, action) (count_over_time({source_channel="auth_log"} | json [%dd]))' % WINDOW_DAYS)
auth_user_action = defaultdict(lambda: defaultdict(int))
for r in res:
    a = r.get("metric", {}).get("actor", "")
    act = r.get("metric", {}).get("action", "")
    if a:
        auth_user_action[a][act] = int(float(r["value"][1]))

if auth_user_action:
    print("| Actor | session_opened | session_closed | auth_failure |")
    print("|---|---:|---:|---:|")
    for actor, acts in sorted(auth_user_action.items(), key=lambda x: -sum(x[1].values())):
        print(f"| `{actor}` | {acts.get('session_opened',0)} | {acts.get('session_closed',0)} | {acts.get('auth_failure',0)} |")
        snapshot["users"].setdefault(actor, {})["sessions_opened_7d"] = acts.get('session_opened',0)
        snapshot["users"][actor]["auth_failures_7d"] = acts.get('auth_failure',0)

# ===== 7. Source IPs per actor (from message_excerpt regex) =====
print("\n## 7. Login source IP diversity per actor\n")
samples = lq_range_lines('{source_channel="auth_log", action="session_opened"}', limit=3000)
ips_by = defaultdict(set)
import re
RH = re.compile(r"rhost=([\d.]+)|from ([\d.]+)| (\d+\.\d+\.\d+\.\d+) port")
for _, line, _ in samples:
    try:
        rec = json.loads(line)
        actor = rec.get("actor") or ""
        msg = rec.get("message_excerpt") or ""
    except Exception:
        continue
    if not actor: continue
    m = RH.search(msg)
    if m:
        ip = m.group(1) or m.group(2) or m.group(3)
        if ip and not ip.startswith(("127.","0.")):
            ips_by[actor].add(ip)

if ips_by:
    print("| Actor | # distinct IPs | Sample |")
    print("|---|---:|---|")
    for actor, ips in sorted(ips_by.items(), key=lambda x: -len(x[1])):
        sample = ", ".join(list(ips)[:5])
        if len(ips) > 5: sample += f", … (+{len(ips)-5})"
        print(f"| `{actor}` | {len(ips)} | {sample} |")
        snapshot["users"].setdefault(actor, {})["distinct_login_ips_7d"] = len(ips)
        snapshot["users"][actor]["login_ips_sample"] = sorted(ips)[:10]
else:
    print("_No IP-resolvable session_opened lines in sample window._\n")

# ===== 8. Anomaly preview =====
print("\n## 8. Outlier preview (observation only — NOT alerts)\n")
flags = []
for user, info in snapshot["users"].items():
    if info.get("late_night_pct", 0) > 25:
        flags.append(f"- ⚠ `{user}` 在 00–06 時段佔活動 **{info['late_night_pct']}%**（一般員工 <5%）")
    if info.get("weekend_pct", 0) > 30:
        flags.append(f"- ⚠ `{user}` 週末活動佔 **{info['weekend_pct']}%**")
    if info.get("auth_failures_7d", 0) > 10:
        flags.append(f"- ⚠ `{user}` 7d 內 auth_failure {info['auth_failures_7d']} 次（帳號可能被掃 / 重試）")
    if info.get("distinct_login_ips_7d", 0) > 5:
        flags.append(f"- ⚠ `{user}` 從 **{info['distinct_login_ips_7d']}** 個不同 IP 登入")

if flags:
    print("\n".join(flags))
else:
    print("_無明顯離群。Baseline data 看起來穩定，threshold 待 1-2 週後再校準。_")

# ===== Snapshot for dashboard reuse =====
os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
with open(JSON_OUT, "w") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)
print(f"\n---\n_Snapshot JSON: `{JSON_OUT}`_")
