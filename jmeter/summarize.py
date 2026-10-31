"""Summarize JMeter results (Lab 2 Part 5).

    python jmeter/summarize.py jmeter/results

Reads <endpoint>_<users>.jtl (JMeter CSV) files and writes, next to them:
  summary.csv                         one row per endpoint and level
  summary.md                          the report tables
  response_time_vs_concurrency.png    average response time vs concurrency
                                      (needs matplotlib: pip install matplotlib)

Per run: samples, average and p50/p95/p99 response time, throughput
(successful + failed requests per second over the run's wall time) and
error rate (samples JMeter marked unsuccessful, i.e. failed assertions,
timeouts and connection errors).
"""
import csv
import re
import statistics
import sys
from pathlib import Path

LABELS = {"login": "Login", "search": "Job search", "apply": "Application submission",
          "event": "Event search", "assistant": "Assistant chat"}
ORDER = ["login", "search", "apply", "event", "assistant"]


def percentile(values, q):
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def load(path: Path) -> dict | None:
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("elapsed")]
    if not rows:
        return None
    elapsed = [int(r["elapsed"]) for r in rows]
    starts = [int(r["timeStamp"]) for r in rows]
    ends = [s + e for s, e in zip(starts, elapsed)]
    wall = max(1, max(ends) - min(starts)) / 1000
    errors = sum(r["success"].lower() != "true" for r in rows)
    codes = {}
    for r in rows:
        codes[r["responseCode"]] = codes.get(r["responseCode"], 0) + 1
    return {"samples": len(rows), "avg_ms": statistics.mean(elapsed),
            "p50_ms": percentile(elapsed, 50), "p95_ms": percentile(elapsed, 95),
            "p99_ms": percentile(elapsed, 99), "max_ms": max(elapsed),
            "throughput_rps": len(rows) / wall, "error_pct": 100 * errors / len(rows),
            "codes": codes}


def main(folder):
    folder = Path(folder)
    results = {}
    for path in folder.glob("*.jtl"):
        m = re.fullmatch(r"([a-z]+)_(\d+)\.jtl", path.name)
        if m and m.group(1) in LABELS:
            stats = load(path)
            if stats:
                results.setdefault(m.group(1), {})[int(m.group(2))] = stats
    if not results:
        sys.exit(f"No <endpoint>_<users>.jtl files in {folder}")

    with open(folder / "summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["endpoint", "users", "samples", "avg_ms", "p50_ms", "p95_ms", "p99_ms",
                    "max_ms", "throughput_rps", "error_pct"])
        for ep in [e for e in ORDER if e in results]:
            for users, s in sorted(results[ep].items()):
                w.writerow([ep, users, s["samples"]] + [round(s[k], 2) for k in
                           ("avg_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "throughput_rps", "error_pct")])

    lines = ["# JMeter results (Pair 15)", ""]
    crud = [e for e in ORDER if e in results and e != "assistant"]
    if crud:
        lines += ["## CRUD endpoints", "",
                  "| Endpoint | Users | Samples | Avg (ms) | p95 (ms) | Throughput (req/s) | Error % |",
                  "|---|---|---|---|---|---|---|"]
        for ep in crud:
            for users, s in sorted(results[ep].items()):
                lines.append(f"| {LABELS[ep]} | {users} | {s['samples']} | {s['avg_ms']:.0f} | "
                             f"{s['p95_ms']:.0f} | {s['throughput_rps']:.1f} | {s['error_pct']:.2f} |")
    if "assistant" in results:
        lines += ["", "## Assistant endpoint", "",
                  "| Users | Samples | p50 (ms) | p95 (ms) | p99 (ms) | Avg (ms) | Throughput (req/s) | Error % |",
                  "|---|---|---|---|---|---|---|---|"]
        for users, s in sorted(results["assistant"].items()):
            lines.append(f"| {users} | {s['samples']} | {s['p50_ms']:.0f} | {s['p95_ms']:.0f} | "
                         f"{s['p99_ms']:.0f} | {s['avg_ms']:.0f} | {s['throughput_rps']:.2f} | "
                         f"{s['error_pct']:.2f} |")
    lines += ["", "Response codes per run:", ""]
    for ep in [e for e in ORDER if e in results]:
        for users, s in sorted(results[ep].items()):
            lines.append(f"- {LABELS[ep]} @ {users}: {s['codes']}")
    (folder / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed: pip install matplotlib for the chart)")
        return
    fig, axes = plt.subplots(1, 2 if "assistant" in results else 1, figsize=(13, 5), squeeze=False)
    ax = axes[0][0]
    for ep in crud:
        xs = sorted(results[ep])
        ax.plot(xs, [results[ep][x]["avg_ms"] for x in xs], marker="o", label=LABELS[ep])
    ax.set(title="CRUD endpoints: average response time vs concurrency",
           xlabel="Concurrent users", ylabel="Average response time (ms)")
    ax.grid(alpha=0.3)
    ax.legend()
    if "assistant" in results:
        ax = axes[0][1]
        xs = sorted(results["assistant"])
        for key, label in (("avg_ms", "average"), ("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99")):
            ax.plot(xs, [results["assistant"][x][key] / 1000 for x in xs], marker="o", label=label)
        ax.set(title="Assistant: response time vs concurrency",
               xlabel="Concurrent users", ylabel="Response time (s)")
        ax.grid(alpha=0.3)
        ax.legend()
    fig.tight_layout()
    fig.savefig(folder / "response_time_vs_concurrency.png", dpi=150)
    print(f"\nWrote {folder / 'response_time_vs_concurrency.png'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "jmeter/results")
