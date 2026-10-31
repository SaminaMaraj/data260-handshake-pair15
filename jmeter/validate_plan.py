"""Smoke-test p15_load_test.jmx without JMeter: one virtual user per group.

Reads the plan, fills every request from the CSV files exactly as JMeter
would (${var}, ${__P(name,default)}, ${__threadNum}, ${__counter(...)}),
sends a few iterations to the gateway, and applies the plan's own response
assertions. Run it before a real load test to catch a wrong path, body,
token or CSV column in seconds.

    python jmeter/validate_plan.py --base http://localhost:9150 --iterations 3
"""
import argparse
import csv
import itertools
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).parent


def props(node):
    return {p.get("name"): (p.text or "") for p in node if p.tag.endswith("Prop") and p.get("name")}


def resolve(text, variables, counter):
    text = re.sub(r"\$\{__P\(([^,)]+),([^)]*)\)\}", lambda m: variables.get("__P:" + m.group(1), m.group(2)), text)
    text = text.replace("${__threadNum}", "1")
    text = re.sub(r"\$\{__counter\([^)]*\)\}", str(counter), text)
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda m: str(variables.get(m.group(1), m.group(0))), text)


def groups(plan_path):
    root = ET.parse(plan_path).getroot()
    top = list(root.find("hashTree").find("hashTree"))
    for element, children in zip(top[::2], top[1::2]):
        if element.tag != "ThreadGroup":
            continue
        items = list(children)
        group = {"name": element.get("testname"), "csv": [], "headers": [], "samplers": []}
        for item, sub in zip(items[::2], items[1::2]):
            p = props(item)
            if item.tag == "CSVDataSet":
                group["csv"].append((p["filename"], p["variableNames"].split(",")))
            elif item.tag == "HeaderManager":
                for h in item.iter("elementProp"):
                    hp = props(h)
                    group["headers"].append((hp["Header.name"], hp["Header.value"]))
            elif item.tag == "HTTPSamplerProxy":
                body = next((props(a).get("Argument.value") for a in item.iter("elementProp")
                             if a.get("elementType") == "HTTPArgument"), None)
                assertion = next((props(a).get("codes") for s in sub.iter("ResponseAssertion")
                                  for a in s.iter("collectionProp") for _ in [0]), None)
                pattern = next((x.text for x in sub.iter("stringProp") if x.get("name") == "codes"), ".*")
                group["samplers"].append({"name": item.get("testname"), "method": p["HTTPSampler.method"],
                                          "path": p["HTTPSampler.path"], "body": body, "expect": pattern})
        yield group


def rows(filename, data_dir):
    path = Path(filename.replace("${__P(data_dir,data)}", str(data_dir)))
    with open(path) as fh:
        reader = csv.reader(fh)
        next(reader)
        return list(reader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:9150")
    parser.add_argument("--plan", default=str(HERE / "p15_load_test.jmx"))
    parser.add_argument("--data-dir", default=str(HERE / "data"))
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    failures = 0
    for group in groups(args.plan):
        feeds = [(names, itertools.cycle(rows(f, args.data_dir))) for f, names in group["csv"]]
        for n in range(1, args.iterations + 1):
            variables = {}
            for names, feed in feeds:
                variables.update(zip(names, next(feed)))
            for s in group["samplers"]:
                url = args.base + resolve(s["path"], variables, n)
                body = resolve(s["body"], variables, n).encode() if s["body"] else None
                headers = {"Content-Type": "application/json",
                           **{k: resolve(v, variables, n) for k, v in group["headers"]}}
                req = urllib.request.Request(url, data=body, headers=headers, method=s["method"])
                started = time.perf_counter()
                try:
                    with urllib.request.urlopen(req, timeout=300) as res:
                        code, payload = res.status, res.read()
                except urllib.error.HTTPError as err:
                    code, payload = err.code, err.read()
                ms = (time.perf_counter() - started) * 1000
                ok = re.fullmatch(s["expect"], str(code)) is not None
                failures += not ok
                try:
                    data = json.loads(payload)
                    detail = (f"{len(data)} results" if isinstance(data, list)
                              else data.get("status") or data.get("detail") or list(data)[:3])
                except ValueError:
                    detail = payload[:60]
                print(f"[{'PASS' if ok else 'FAIL'}] {group['name']:24} {s['method']:4} "
                      f"{url.replace(args.base, ''):60.60} -> {code} ({s['expect']}) {ms:7.0f} ms  {detail}")
    print(f"\n{'OK' if not failures else str(failures) + ' FAILED'}: plan requests validated against {args.base}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
