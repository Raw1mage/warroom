#!/usr/bin/env bash
# Walk every dashboard, run each panel's target query, classify empty results.
# Robust panel walk: includes nested `row.panels[]` of collapsed rows.
set -uo pipefail
LOKI=http://localhost:3100
NOW=$(date +%s)
WINDOW_24H_NS_START=$((NOW - 86400))000000000
WINDOW_7D_NS_START=$((NOW - 7*86400))000000000
NOW_NS=${NOW}000000000

sub_vars() {
  sed -E 's/\$__range/24h/g; s/\$__rate_interval/1m/g; s/\$interval/1m/g; s/\$__interval/1m/g; s/\$nas/thesmart/g'
}

probe_loki() {
  curl -s -G "$LOKI/loki/api/v1/query_range" \
    --data-urlencode "query=$1" --data-urlencode "start=$2" \
    --data-urlencode "end=$NOW_NS" --data-urlencode 'limit=1' 2>/dev/null
}

probe_prom() {
  docker exec warroom-prometheus sh -c "wget -qO- \"http://localhost:9090/api/v1/query?query=\$(printf %s '$1' | tr ' ' '+')\"" 2>/dev/null
}

count_of() {
  jq -r '
    if (.data.resultType // "") == "vector" then
      (.data.result | length)
    elif (.data.resultType // "") == "matrix" then
      ([.data.result[]?.values] | flatten | length)
    elif (.data.resultType // "") == "streams" then
      ([.data.result[]?.values] | flatten | length)
    else 0
    end
  ' <<< "$1" 2>/dev/null
}

err_of() {
  jq -r '.error // empty' <<< "$1" 2>/dev/null
}

for f in ~/projects/warroom/grafana/dashboards/*.json ~/projects/warroom/grafana/dashboards-sunshine/*.json; do
  fname=$(basename "$f")
  title=$(jq -r '.title' "$f")
  echo "================================================================================"
  echo "$fname  ($title)"
  echo "================================================================================"
  panels=0; empty24=0; empty7d=0; bugs=0

  # one TSV line per (panel_id, panel_title, ds_type, expr)
  while IFS=$'\t' read -r pid ptitle ds expr; do
    [ -z "$expr" ] && continue
    [ "$expr" = "null" ] && continue
    expr_subst=$(echo "$expr" | sub_vars)
    panels=$((panels+1))

    if [ "$ds" = "loki" ]; then
      resp=$(probe_loki "$expr_subst" "$WINDOW_24H_NS_START")
      err=$(err_of "$resp"); cnt=$(count_of "$resp")
      if [ -n "$err" ]; then
        echo "  CONFIG_BUG  p#$pid  $ptitle"
        echo "    err: $err"
        echo "    expr: $(echo "$expr_subst" | head -c 200)"
        bugs=$((bugs+1))
      elif [ "${cnt:-0}" = "0" ]; then
        resp7=$(probe_loki "$expr_subst" "$WINDOW_7D_NS_START")
        cnt7=$(count_of "$resp7")
        if [ "${cnt7:-0}" = "0" ]; then
          echo "  NO_DATA_7d  p#$pid  $ptitle"
          echo "    expr: $(echo "$expr_subst" | head -c 200)"
          empty7d=$((empty7d+1))
        else
          echo "  EMPTY_24h   p#$pid  $ptitle  (7d has $cnt7)"
          empty24=$((empty24+1))
        fi
      fi
    elif [ "$ds" = "prometheus" ]; then
      resp=$(probe_prom "$expr_subst")
      err=$(err_of "$resp"); cnt=$(count_of "$resp")
      if [ -n "$err" ]; then
        echo "  CONFIG_BUG  p#$pid  $ptitle"
        echo "    err: $err"
        echo "    expr: $(echo "$expr_subst" | head -c 200)"
        bugs=$((bugs+1))
      elif [ "${cnt:-0}" = "0" ]; then
        echo "  NO_DATA_pr  p#$pid  $ptitle"
        echo "    expr: $(echo "$expr_subst" | head -c 200)"
        empty7d=$((empty7d+1))
      fi
    fi
  done < <(jq -r '
    def walk_panels:
      .[]? | if .type=="row" then (.panels // []) | walk_panels else (., empty) end;
    def all_targets:
      .panels // [] | walk_panels
      | select(.type != "row")
      | (.id as $pid | .title as $ptitle | .datasource.type as $panel_ds
         | (.targets // [])[]
         | [$pid, $ptitle,
            (.datasource.type // $panel_ds // ""),
            (.expr // "")]
         | @tsv);
    all_targets
  ' "$f" 2>/dev/null)

  echo "  -> $panels targets / $empty24 empty-24h / $empty7d no-data-7d / $bugs config-bug"
  echo
done
