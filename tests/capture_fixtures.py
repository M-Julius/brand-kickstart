#!/usr/bin/env python3
"""Live helper (not a unittest): verify each platform's rule on real names and save fixtures.

Usage:
    python3 -I tests/capture_fixtures.py [platform ...] [--raw-dir DIR]

For every platform with a request URL it fetches several known-taken names and random
free names, prints how each response classifies against platforms.json, and saves the
canary pair as tests/fixtures/<key>_<taken|free>.<ext> plus a .meta.json sidecar.
Standard library only. --raw-dir keeps full untrimmed bodies, which
helps when looking for a new marker.
"""
import argparse
import json
import random
import re
import string
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "brand-kickstart" / "scripts"))
import check  # noqa: E402

FIXTURES = HERE / "fixtures"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TRIM = 150_000
EXTRA_TAKEN = {
    "instagram": ["nike", "natgeo", "nasa", "therock", "bbcnews", "spotify", "google",
                  "cristiano"],
    "tiktok": ["khaby.lame", "tiktok", "nba"],
    "youtube": ["mkbhd", "google", "nasa", "tedx"],
    "x": ["nasa", "google", "elonmusk", "nytimes"],
    "github": ["torvalds", "google", "microsoft", "facebook"],
    "npm": ["lodash", "express", "vue", "axios"],
    "pypi": ["numpy", "django", "flask", "pandas"],
    "facebook": ["barackobama", "cocacola", "tokopedia", "indomie", "natgeo"],
    "threads": ["instagram", "mosseri", "netflix", "natgeo", "nasa"],
}


def get(url, plain):
    ua = check.PLAIN_UA if plain else UA
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), resp.geturl(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), url, dict(e.headers)


def verdict(p, status, body):
    c = p["check"]
    if c["type"] == "status":
        return "taken" if status in c["taken"] else "available" if status in c["available"] else f"?{status}"
    if c["type"] == "json":
        try:
            v = json.loads(body).get(c["field"])
        except ValueError:
            return f"?{status}"
        if v in c.get("invalid", []):
            return "invalid"
        return "taken" if v in c["taken"] else "available" if v in c["available"] else f"?{v}"
    if re.search(c["taken_regex"], body):
        return "taken"
    if c.get("available_regex") and re.search(c["available_regex"], body):
        return "available"
    return f"?{status}"


def trim(key, p, body):
    if p["check"]["type"] == "status":
        return body[:2000]  # status decides; the body is only context
    if p["check"]["type"] == "body":  # keep the start plus the marker region only
        parts = [body[:5000]]
        for rx in (p["check"]["taken_regex"], p["check"].get("available_regex")):
            m = rx and re.search(rx, body)
            if m:
                parts.append(body[max(0, m.start() - 1000): m.end() + 1000])
        return "\n<!-- trimmed -->\n".join(parts)
    return body[:TRIM]


def rand_name():
    return "".join(random.choice(string.ascii_lowercase) for _ in range(11))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("platforms", nargs="*")
    ap.add_argument("--raw-dir")
    args = ap.parse_args()
    platforms = check.load_platforms()
    keys = args.platforms or [k for k, p in platforms.items() if "url" in p]
    FIXTURES.mkdir(exist_ok=True)
    raw = Path(args.raw_dir) if args.raw_dir else None
    if raw:
        raw.mkdir(parents=True, exist_ok=True)
    bad = 0
    for key in keys:
        p = platforms[key]
        plain = p.get("user_agent") == "plain"
        ext = "json" if p["check"]["type"] == "json" or "registry.npmjs" in p["url"] or "/json" in p["url"] else "html"
        cases = [("taken", p["canary"]["taken"], True), ("free", p["canary"]["available"], True)]
        cases += [("taken", n, False) for n in EXTRA_TAKEN.get(key, [])]
        cases += [("free", rand_name(), False) for _ in range(5)]
        for want, name, save in cases:
            status, body, final, headers = get(p["url"].format(name=name), plain)
            got = verdict(p, status, body)
            ok = got == ("available" if want == "free" else "taken") or (want == "taken" and got == "invalid")
            bad += not ok
            print(f"{'ok ' if ok else 'BAD'} {key:10} want={want:5} got={got:12} http={status} size={len(body)} {name}")
            if raw:
                (raw / f"{key}_{want}_{name}.{ext}").write_text(body, encoding="utf-8")
            if save:
                f = FIXTURES / f"{key}_{want}.{ext}"
                f.write_text(trim(key, p, body), encoding="utf-8")
                meta = {"status": status, "url": final,
                        "headers": {k.lower(): v for k, v in headers.items() if k.lower() == "retry-after"}}
                Path(str(f) + ".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"\n{bad} unexpected result(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
