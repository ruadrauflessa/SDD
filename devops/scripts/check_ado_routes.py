"""Checks every Azure DevOps call devops.py makes against ADO's own route table.

    python devops/scripts/check_ado_routes.py [--org dnceng-public]     (needs network; no sign-in)

Runs test_devops.py with the offline ADO logging each call (DEVOPS_FAKE_LOG), reads the route table ADO
serves to anyone (`OPTIONS https://dev.azure.com/<org>/_apis/`), and says for each distinct call whether
it is a route ADO serves at the api-version devops sends. Not part of the offline checks: it needs the
network. Exit 1 when a call has no route.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def route_rx(r):
    t = r["routeTemplate"].replace("{area}", r["area"]).replace("{resource}", r["resourceName"])
    parts = t.split("/")
    param = lambda p: re.fullmatch(r"\{\*?[^}]+\}", p)
    seg = lambda p: "[^/]+" if param(p) else re.escape(p)
    req = len(parts)
    while req > 0 and param(parts[req - 1]):  # trailing ids are optional
        req -= 1
    lead = 0
    while lead < req and re.fullmatch(r"\{(project|team)\}", parts[lead]):  # so are a leading project and team
        lead += 1
    s = "".join("(?:" + seg(p) + "/)?" for p in parts[:lead]) + "/".join(seg(p) for p in parts[lead:req])
    s += "".join("(?:/" + seg(p) + ")?" for p in parts[req:])
    return re.compile("^" + s + "$", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default="dnceng-public", help="any organization; the route table is the same service")
    a = ap.parse_args()
    req = urllib.request.Request(f"https://dev.azure.com/{a.org}/_apis/", method="OPTIONS")
    with urllib.request.urlopen(req, timeout=60) as r:
        routes = json.loads(r.read())["value"]
    fd, log = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        env = dict(os.environ, DEVOPS_FAKE_LOG=log)
        r = subprocess.run([sys.executable, str(HERE / "test_devops.py")], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout + r.stderr)
            return 2
        calls = [json.loads(x) for x in Path(log).read_text(encoding="utf-8").splitlines() if x.strip()]
    finally:
        os.unlink(log)
    compiled = [(r, route_rx(r)) for r in routes]
    seen = {}
    for c in calls:
        u = urllib.parse.urlsplit(c["url"])
        tail = urllib.parse.unquote(u.path).split("/", 2)[2]
        seen.setdefault((c["method"], re.sub(r"/\d+", "/{id}", tail)), (tail, dict(urllib.parse.parse_qsl(u.query)).get("api-version")))
    bad = 0
    for (method, shape), (tail, ver) in sorted(seen.items(), key=lambda kv: kv[0][1]):
        good = [r for r, x in compiled if x.match(tail) and float(r["maxVersion"]) >= float(ver)]
        bad += not good
        name = f"{good[0]['area']}/{good[0]['resourceName']}" if good else ""
        print(f"{'OK     ' if good else 'MISSING'} {method:5} {shape:62} {name}")
    print(f"{len(seen)} distinct calls, {len(routes)} ADO routes: "
          + ("every call is a route ADO serves" if not bad else f"{bad} with no route"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
