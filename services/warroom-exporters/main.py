"""
Warroom unified exporter container — runs 3 logical exporters in threads:

  :9117  asusrouter         (ssh /proc /nvram /iptables → Prometheus)
  :9118  geoip-enrich       (mmdb lookup + /lookup HTTP API + /metrics)
  :9119  securityscan       (ssh /var/lib/securityscan → Prometheus)

Each module exposes a `run()` callable that starts its HTTPServer. We launch
them as daemon threads so the container's PID 1 stays in main() and exits
cleanly on SIGTERM.
"""
import importlib
import signal
import sys
import threading


def _start(module_name, port):
    mod = importlib.import_module(module_name)
    # All three exporters use BaseHTTPRequestHandler subclasses under module-level
    # `Handler` and serve on HTTPServer((0.0.0.0, PORT), Handler). We re-invoke
    # them by calling their `_main` or constructing the server here.
    from http.server import HTTPServer
    # Initialize module state if it provides _init_dbs
    if hasattr(mod, "_init_dbs"):
        mod._init_dbs()
    # Optional background feeders
    if hasattr(mod, "feeder_loop"):
        threading.Thread(target=mod.feeder_loop, daemon=True).start()
    print(f"[{module_name}] listening :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), mod.Handler).serve_forever()


def main():
    threads = []
    for module, port in [("router", 9117), ("geoip", 9118), ("security", 9119)]:
        t = threading.Thread(target=_start, args=(module, port), daemon=True, name=f"exporter-{module}")
        t.start()
        threads.append(t)

    # Hold PID 1 forever; signal handler exits cleanly so docker stop is fast.
    def _quit(*_):
        print("shutdown signal received", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _quit)
    signal.signal(signal.SIGINT, _quit)
    signal.pause()


if __name__ == "__main__":
    main()
