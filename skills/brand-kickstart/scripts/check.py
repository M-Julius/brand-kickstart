#!/usr/bin/env python3
"""brand-kickstart: check whether a brand or project name is free across platforms and domains.

Standard library only, no packages to install. Platform definitions live in platforms.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

PLATFORMS_PATH = Path(__file__).resolve().parent / "platforms.json"
MAX_VARIANTS = 12
MAX_BODY = 1_000_000
DEFAULT_INTERVAL = 0.3
RETRY_WAIT = 5
MAX_RETRY_WAIT = 60
_HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Letters NFKD cannot split into base + accent; without this they would silently vanish.
_TRANSLIT = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d",
                           "ð": "d", "þ": "th", "ı": "i", "Ø": "o", "Æ": "ae", "Œ": "oe",
                           "Ł": "l", "Đ": "d", "Ð": "d", "Þ": "th"})
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
# Platforms with "user_agent": "plain" (Instagram, Facebook) serve an error page to a client that claims to
# be Chrome without Chrome's TLS fingerprint, and the real page to a client that says what it is.
PLAIN_UA = "brand-kickstart/0.1 (+https://github.com/M-Julius/brand-kickstart)"
# Bodies of 403s written by a sandbox's egress proxy rather than by the site itself.
_SANDBOX_RE = re.compile(r"sessions are bound to their configured repositories|__agentproxy|"
                         r"[Hh]ost not (?:in|on) (?:the )?allow ?list|[Dd]omain (?:is )?not allowed|"
                         r"blocked by (?:the )?(?:egress|sandbox|network) (?:proxy|policy)")
_LOGIN_RE = re.compile(r"(?:^|/)(?:accounts/)?login(?:\.php)?(?:/|$)")
# Reasons that mean "this source gave no answer, stop asking it".
STOP_REASONS = ("rate_limited", "blocked", "sandbox_blocked", "login_wall")


@dataclass
class Response:
    status: int  # 0 = network error; the error text is in body
    body: str
    url: str
    headers: dict = field(default_factory=dict)


def fetch(url: str, user_agent: str | None = None, timeout: float = 10.0) -> Response:
    """GET a URL. Never raises: HTTP errors come back as a Response, network errors as status 0."""
    req = urllib.request.Request(url, headers={**HEADERS, **({"User-Agent": user_agent} if user_agent else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_BODY).decode("utf-8", "replace")
            return Response(resp.status, body, resp.geturl(), {k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        body = e.read(MAX_BODY).decode("utf-8", "replace")
        return Response(e.code, body, e.geturl() or url, {k.lower(): v for k, v in e.headers.items()})
    except Exception as e:  # URLError, timeout, connection reset, bad TLS...
        return Response(0, str(e), url)


def classify(platform: dict, resp: Response):
    """Map a response to (status, reason). No clear signal is always unknown, never a guess."""
    c = platform["check"]
    if c["type"] == "manual_only":
        return "unknown", "manual_only"
    if resp.status == 0:
        return "unknown", "network_error"
    if resp.status in (429, 503):
        return "unknown", "rate_limited"
    if resp.status >= 500:  # transient server trouble, e.g. X's 500 "Internal error" (code 131)
        return "unknown", "server_error"
    # A sandbox proxy (Claude.ai, ChatGPT) answers for the site with its own 403: the site never saw it.
    if resp.status in (403, 407) and _SANDBOX_RE.search(resp.body):
        return "unknown", "sandbox_blocked"
    # Redirected to another host (consent page, interstitial): that page says nothing about the name.
    if urlsplit(resp.url).hostname not in {urlsplit(platform["url"]).hostname, *platform.get("hosts", [])}:
        return "unknown", "blocked"
    # Sent to a login page (Instagram, Facebook do this to cloud/datacenter IPs): no answer about the name.
    # Threads is the exception: its login page *is* the answer for a free name ("login_is_answer").
    if (not c.get("login_is_answer") and _LOGIN_RE.search(urlsplit(resp.url).path)
            and not _LOGIN_RE.search(urlsplit(platform["url"]).path)):
        return "unknown", "login_wall"
    if (resp.status == 403
            or (c.get("blocked_regex") and re.search(c["blocked_regex"], resp.body))):
        return "unknown", "blocked"
    if c["type"] == "status":
        if resp.status in c["taken"]:
            return "taken", None
        if resp.status in c["available"]:
            # e.g. Facebook's Graph API only sees public Pages, so a 404/400 there cannot rule out a profile
            return ("unknown", "likely_free") if c.get("available_unconfirmed") else ("available", None)
    elif c["type"] == "json":
        try:
            data = json.loads(resp.body)
        except ValueError:
            return "unknown", "unexpected_response"
        value = data.get(c["field"]) if isinstance(data, dict) else None
        if value in c["taken"]:
            return "taken", None
        if value in c["available"]:
            return "available", None
        if value in c.get("invalid", []):
            return "invalid", f"rule:{data.get('desc') or value}"
    elif c["type"] == "body":
        if re.search(c["taken_regex"], resp.body):
            return "taken", None
        if c.get("available_regex") and re.search(c["available_regex"], resp.body):
            # the "free" page also shows for names that exist but are hidden (e.g. Facebook age-restricted pages)
            return ("unknown", "likely_free") if c.get("available_unconfirmed") else ("available", None)
    return "unknown", "unexpected_response"


def load_platforms(path: Path = PLATFORMS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tokenize(name: str) -> list:
    """Split a name into lowercase ASCII word tokens ("Kopi Café" -> ["kopi", "cafe"])."""
    decomposed = unicodedata.normalize("NFKD", name.translate(_TRANSLIT))
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    lost = [c for c in ascii_only if unicodedata.category(c).startswith("L") and not c.isascii()]
    if lost:
        raise ValueError(f"{name!r}: letters {''.join(dict.fromkeys(lost))} cannot be used in handles")
    return re.findall(r"[a-z0-9]+", ascii_only.lower())


def to_handle(name: str) -> str:
    """An exact handle ("acmestudio.id") is kept; free text ("Acme Studio") is joined."""
    stripped = name.strip().strip("._-")
    if stripped and _HANDLE_RE.match(stripped):
        return stripped.lower()
    return "".join(tokenize(name))


def rule_error(platform: dict, handle: str):
    """Return a reason text if `handle` breaks the platform's naming rule, else None."""
    if re.fullmatch(platform["rule"]["pattern"], handle):
        return None
    return f"not allowed on {platform['name']}"


def variants(tokens: list, mode: str, country) -> list:
    """Common handle variants, base form first, de-duplicated, capped at MAX_VARIANTS."""
    base = "".join(tokens)
    joiners = ["", ".", "_", "-"] if len(tokens) > 1 else [""]
    out = [j.join(tokens) for j in joiners]
    if country:
        out += [f"{base}.{country}", f"{base}_{country}"]
    out += [f"{base}official", f"{base}hq", f"the{base}"]
    if mode == "project":
        out += [f"get{base}", f"{base}app"]
    return list(dict.fromkeys(out))[:MAX_VARIANTS]


IANA_BOOTSTRAP = "https://data.iana.org/rdap/dns.json"


def load_bootstrap(fetch) -> "dict | None":
    """TLD -> RDAP base URL from IANA. None when it cannot be downloaded or parsed."""
    resp = fetch(IANA_BOOTSTRAP)
    if resp.status != 200:
        return None
    try:
        services = json.loads(resp.body)["services"]
        return {tld.lower(): urls[0] for tlds, urls in services for tld in tlds}
    except (ValueError, KeyError, IndexError, TypeError):
        return None


IANA_WHOIS = "whois.iana.org"
WHOIS_SUFFIX = {"whois.jprs.jp": "/e"}  # JPRS answers in Japanese without it
_WHOIS_AVAILABLE = re.compile(
    r"DOMAIN NOT FOUND|Domain not found\.|No Data Found|No match for \"|^Status:\s*free"
    r"|No match!!|is available for registration", re.I | re.M)
_WHOIS_SERVERS: dict = {}


def whois_query(server: str, query: str, timeout: float = 10.0) -> str:
    """Raw WHOIS (RFC 3912) over TCP port 43. Raises OSError on network failure."""
    with socket.create_connection((server, 43), timeout=timeout) as conn:
        conn.sendall(query.encode("ascii") + b"\r\n")  # labels are ASCII after tokenize()
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", "replace")


def classify_whois(domain: str, body: str):
    """'available', 'taken', or None when the text proves neither."""
    if _WHOIS_AVAILABLE.search(body):
        return "available"
    name = re.escape(domain)
    if re.search(rf"(?im)^\s*(?:domain name|domain|\[domain name\])\s*:?\s*{name}\s*$", body):
        return "taken"
    return None


def _whois_server(tld: str, whois) -> "str | None":
    top = tld.split(".")[-1]  # co.id, com.my -> the national registry answers
    if top not in _WHOIS_SERVERS:
        try:
            m = re.search(r"(?m)^whois:\s*(\S+)", whois(IANA_WHOIS, top))
        except OSError:
            return None  # not cached: a later domain may retry
        _WHOIS_SERVERS[top] = m.group(1) if m else None
    return _WHOIS_SERVERS[top]


def check_domain(label: str, tld: str, bootstrap, fetch, whois=whois_query) -> dict:
    """RDAP at the TLD's own registry; WHOIS when RDAP is missing or failing.

    (rdap.org's 404 cannot tell "free" from "unsupported TLD", so it is never used.)
    """
    domain = f"{label}.{tld}"
    result = {"handle": domain, "platform": f".{tld}", "status": "unknown", "reason": None,
              "url": f"https://www.whois.com/whois/{domain}"}
    base = bootstrap.get(tld.lower()) if bootstrap else None
    if bootstrap is None:
        result["reason"] = "network_error"
    elif not base:
        result["reason"] = "no_rdap"
    else:
        resp = fetch(f"{base.rstrip('/')}/domain/{domain}")
        if resp.status == 200:
            result["status"] = "taken"
            return result
        if resp.status == 404:
            result["status"] = "available"
            return result
        result["reason"] = ("network_error" if resp.status == 0 else
                            "rate_limited" if resp.status in (429, 503) else "unexpected_response")
    server = _whois_server(tld, whois)
    if server:
        try:
            status = classify_whois(domain, whois(server, domain + WHOIS_SUFFIX.get(server, "")))
        except OSError:
            status = None
        if status:
            result.update(status=status, reason=None)
            return result
    # Sandboxes (Claude.ai, ChatGPT) only let HTTPS out, so port 43 fails: ask DNS over HTTPS instead.
    status = _dns_status(domain, fetch)
    if status == "taken":
        result.update(status="taken", reason=None)
    elif status:
        result["reason"] = status
    return result


DOH = "https://dns.google/resolve?name={}&type=NS"


def _dns_status(domain: str, fetch) -> "str | None":
    """'taken' when the domain has name servers; 'likely_free' on NXDOMAIN (a registered domain
    with no name servers looks the same); None when DNS gives no answer."""
    try:
        data = json.loads(fetch(DOH.format(domain)).body)
    except ValueError:
        return None
    if data.get("Status") == 3:
        return "likely_free"
    if data.get("Status") == 0 and any(a.get("type") == 2 for a in data.get("Answer", [])):
        return "taken"
    return None


def _retry_wait(resp: Response) -> int:
    value = resp.headers.get("retry-after", "")
    return min(int(value), MAX_RETRY_WAIT) if value.isdigit() else RETRY_WAIT


def check_platform(key: str, platforms: dict, handles: list, fetch=fetch, sleep=time.sleep) -> dict:
    """Check handles on one platform, one request at a time. Returns handle -> result."""
    p = platforms[key]
    extra = {"timeout": p["timeout"]} if "timeout" in p else {}  # slow, heavy pages (Facebook)
    if p.get("user_agent") == "plain":
        extra["user_agent"] = PLAIN_UA
    interval = p.get("min_interval", DEFAULT_INTERVAL)
    results, todo = {}, []

    def result(handle, status, reason):
        return {"handle": handle, "platform": key, "status": status, "reason": reason,
                "url": p["profile_url"].format(name=handle)}

    for h in dict.fromkeys(handles):
        err = rule_error(p, h)
        if err:
            results[h] = result(h, "invalid", f"rule:{err}")
        else:
            todo.append(h)
    if p["check"]["type"] == "manual_only":
        results.update({h: result(h, "unknown", "manual_only") for h in todo})
        return results

    sent = 0

    def request(handle):
        nonlocal sent
        if sent:
            sleep(interval)
        sent += 1
        url = p["url"].format(name=handle)
        resp = fetch(url, **extra)
        status, reason = classify(p, resp)
        if reason in ("rate_limited", "server_error", "network_error"):  # one retry; only rate limits stop it
            sleep(_retry_wait(resp))
            status, reason = classify(p, fetch(url, **extra))
        return status, reason

    def preflight():
        # A known-taken handle must read as taken, else this IP is being served something else.
        status, reason = request(p["canary"]["taken"])
        if status == "taken":
            return None
        return reason if reason in STOP_REASONS or reason == "network_error" else "blocked"

    stop = preflight() if todo and p.get("preflight") else None
    via = None
    if todo and stop and p.get("fallback"):
        # The main page is walled off from this IP; a second public source (e.g. Facebook's Graph API) may answer.
        primary_stop = stop
        p = {**p, **p["fallback"]}
        extra = {"timeout": p["timeout"]} if "timeout" in p else {}
        if p.get("user_agent") == "plain":
            extra["user_agent"] = PLAIN_UA
        interval = p.get("min_interval", DEFAULT_INTERVAL)
        stop = preflight()
        via = "fallback" if not stop else None
        stop = stop and primary_stop  # report why the main page failed, not the fallback
    for h in todo:
        if stop:
            results[h] = result(h, "unknown", stop)
            continue
        status, reason = request(h)
        results[h] = result(h, status, reason)
        if via:
            results[h]["via"] = p["fallback_name"] if "fallback_name" in p else "fallback"
        if reason in STOP_REASONS:
            stop = reason
    return results


def _check_domains(pairs: list, tlds: list, fetch, sleep) -> dict:
    """(label, tld) -> result; bootstrap is fetched once, requests are paced."""
    out = {}
    if not pairs:
        return out
    bootstrap = load_bootstrap(fetch)
    for i, (label, tld) in enumerate(pairs):
        if i and bootstrap and bootstrap.get(tld):
            sleep(DEFAULT_INTERVAL)
        out[(label, tld)] = check_domain(label, tld, bootstrap, fetch)
    return out


def run(entries: list, keys: list, tlds: list, platforms: dict, fetch=fetch, sleep=time.sleep) -> list:
    """Check every entry on every selected platform and TLD. Platforms run in parallel."""
    handles = list(dict.fromkeys(e["handle"] for e in entries))
    source = {k: platforms[k]["check"]["platform"] if platforms[k]["check"]["type"] == "same_as" else k
              for k in keys}
    # a "held_by" platform (Threads) is read together with its holder (Instagram), so run both
    real = list(dict.fromkeys([*source.values(), *(platforms[k]["held_by"] for k in keys if "held_by" in platforms[k])]))
    pairs = list(dict.fromkeys((label, t) for e in entries for label in e.get("labels", []) for t in tlds))
    with ThreadPoolExecutor(max_workers=len(real) + 1) as pool:
        jobs = {k: pool.submit(check_platform, k, platforms, handles, fetch, sleep) for k in real}
        domain_job = pool.submit(_check_domains, pairs, tlds, fetch, sleep)
        by_key = {k: job.result() for k, job in jobs.items()}
        domains = domain_job.result()

    out = []
    for e in entries:
        h = e["handle"]
        for k in keys:
            p = platforms[k]
            r = dict(by_key[source[k]][h])
            if source[k] != k:
                r.update(platform=k, url=p["profile_url"].format(name=h))
                err = rule_error(p, h)
                if err:
                    r.update(status="invalid", reason=f"rule:{err}")
            holder = p.get("held_by")
            if holder and r["status"] == "available":
                held = by_key[holder][h]
                if held["status"] == "taken":  # the holder account exists but has not turned this platform on
                    r.update(status="taken", reason=f"held_by:{holder}")
                elif held["status"] != "available":
                    r.update(status=held["status"], reason=held["reason"])
            out.append({"input": e["input"], **r})
        for label in e.get("labels", []):
            for t in tlds:
                out.append({"input": e["input"], **domains[(label, t)]})
    return out


CONFIG_PATH = Path.home() / ".config" / "brand-kickstart" / "config.json"
MODES = ("brand", "project", "all")
ALIASES = {"ig": "instagram", "tt": "tiktok", "yt": "youtube", "twitter": "x",
           "gh": "github", "ph": "producthunt"}
SYMBOL = {"available": "✅", "taken": "❌", "unknown": "❓", "invalid": "⛔"}
LINK = "🔗"
LIKELY = "✅?"  # the free page showed, but the platform cannot confirm the name is free
HELD = "🔒"  # no profile yet, but the account that holds the name (Instagram for Threads) exists


def _symbol(r: dict) -> str:
    if r.get("reason") == "likely_free":
        return LIKELY
    if (r.get("reason") or "").startswith("held_by:"):
        return HELD
    return LINK if r.get("reason") == "manual_only" else SYMBOL[r["status"]]


def load_config(path=None) -> dict:
    """User preferences. Missing file -> {}; broken file -> warning + {}."""
    path = Path(path or os.environ.get("BRAND_KICKSTART_CONFIG") or CONFIG_PATH)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"warning: ignoring config {path}: {e}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def _keys(platforms: dict, names) -> list:
    keys = [ALIASES.get(n.strip().lower(), n.strip().lower()) for n in names if n.strip()]
    unknown = [k for k in keys if k not in platforms]
    if unknown:
        raise ValueError(f"unknown platform(s): {', '.join(unknown)}. Known: {', '.join(platforms)}")
    return keys


def select_platforms(platforms: dict, mode: str, only, skip) -> list:
    """Platforms to check, in platforms.json order."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}. Use one of: {', '.join(MODES)}")
    skipped = set(_keys(platforms, skip or []))
    if only:
        chosen = set(_keys(platforms, only))
    else:
        chosen = {k for k, p in platforms.items() if mode == "all" or mode in p["modes"]}
    return [k for k in platforms if k in chosen and k not in skipped]


def _source(key: str, platforms: dict) -> str:
    return "domains" if key.startswith(".") else platforms[key]["check"].get("platform", key)


def _hints(results: list, keys: list, platforms: dict) -> list:
    hints = []
    # Only failures where the site itself never answered say anything about the network. A 403, a login
    # page or a 429 came from the platform, so the network was fine and opening more domains will not help.
    def names_for(reasons):
        failed = {_source(r["platform"], platforms) for r in results if r.get("reason") in reasons}
        return sorted(platforms[s]["name"] if s in platforms else "domain lookup" for s in failed)

    unreachable = names_for(("network_error",))
    if len(unreachable) >= 3:
        hints.append(f"{', '.join(unreachable)} could not be reached from this network at all. In a sandbox "
                     "(Claude.ai, ChatGPT) that usually means only package registries are allowed: allow all "
                     "domains for code execution in the app settings, or run the check on your own machine.")
    sandboxed = names_for(("sandbox_blocked",))
    if sandboxed:
        hints.append(f"{', '.join(sandboxed)}: this session's own network proxy refused the request, so the "
                     "platform never saw it. This is a sandbox rule, not a rate limit: waiting or rerunning will "
                     "not help. Open the links, or run the check on your own machine.")
    walled = names_for(("login_wall",))
    if walled:
        hints.append(f"{', '.join(walled)} sent a login page instead of the profile. Platforms do this to cloud "
                     "and datacenter IPs, so waiting rarely helps. Open the links, or run the check on your own "
                     "machine.")
    for r in results:
        reason, key = r.get("reason") or "", r["platform"]
        if reason == "likely_free" and r.get("via"):
            hint = (f"{platforms[key]['name']}'s profile page needed a login, so this was checked through "
                    f"{r['via']}, which only sees public Pages. {LIKELY} means no Page has the name; a personal "
                    f"profile could still hold it. Open the {LIKELY} links to be sure.")
        elif reason.startswith("held_by:"):
            holder = platforms[reason.split(":", 1)[1]]["name"]
            hint = (f"{platforms[key]['name']} handles come with the {holder} account. {HELD} means that {holder} "
                    f"account exists but has not turned on {platforms[key]['name']}: if it is yours, turn on "
                    f"{platforms[key]['name']} and the name is yours; if not, no one else can take it.")
        elif reason == "likely_free" and key.startswith("."):
            hint = (f"WHOIS for {key} could not be reached, so {LIKELY} only means no DNS record was found. "
                    f"Open the {LIKELY} links to be sure.")
        elif reason == "likely_free":
            hint = (f"{platforms[key]['name']} can only confirm taken names: an age-restricted page looks "
                    f"the same as a free name. Open the {LIKELY} links to be sure.")
        elif reason in ("rate_limited", "blocked"):
            if key.startswith("."):
                hint = f"The {key} registry limited requests. Wait a few minutes and rerun."
            else:
                src = platforms[key]["check"].get("platform", key)
                rerun = [k for k in keys if k == src or platforms[k]["check"].get("platform") == src]
                hint = (f"{platforms[src]['name']} limited this IP. Wait a few minutes and rerun with "
                        f"--platforms {','.join(rerun)}")
        else:
            continue
        if hint not in hints:
            hints.append(hint)
    return hints


def display_width(text: str) -> int:
    """Terminal columns: wide characters (the status emoji) take two."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 0 if unicodedata.combining(c) else 1
               for c in text)


def _table(rows: list) -> list:
    """Markdown table that lines up in a terminal (still valid Markdown).

    First column left-aligned; the rest centered with at least two spaces each side.
    """
    widths = [max(display_width(r[i]) for r in rows) for i in range(len(rows[0]))]
    widths = [w if i == 0 else w + 2 for i, w in enumerate(widths)]

    def cell(text, i):
        gap = widths[i] - display_width(text)
        if i == 0:
            return f" {text}{' ' * gap} "
        left = gap // 2
        return f"  {' ' * left}{text}{' ' * (gap - left)}  "

    line = lambda r: "|" + "|".join(cell(t, i) for i, t in enumerate(r)) + "|"  # noqa: E731
    sep = "|" + "|".join("-" * (widths[0] + 2) if i == 0 else ":" + "-" * (w + 2) + ":"
                         for i, w in enumerate(widths)) + "|"
    return [line(rows[0]), sep] + [line(r) for r in rows[1:]]


def render_markdown(results: list, keys: list, tlds: list, platforms: dict) -> str:
    rows = {}  # (input, handle) -> {column: [results]}
    first_row = {}
    for r in results:
        if r["platform"].startswith("."):
            continue
        row_key = (r["input"], r["handle"])
        first_row.setdefault(r["input"], row_key)
        rows.setdefault(row_key, {})[r["platform"]] = [r]
    for r in results:
        if r["platform"].startswith("."):
            row_key = first_row.setdefault(r["input"], (r["input"], to_handle(r["input"])))
            rows.setdefault(row_key, {}).setdefault(r["platform"], []).append(r)

    columns = keys + [f".{t}" for t in tlds]

    def counts(cells):
        return all(c["status"] == "available" or c.get("reason") == "likely_free"
                   for col in cells.values() for c in col if c.get("reason") != "manual_only")

    ordered = sorted(rows.items(), key=lambda item: not counts(item[1]))
    # Platforms down the left, one column per name: grows downward, not sideways.
    labels = [platforms[k]["name"] for k in keys] + [f".{t}" for t in tlds]
    table = [["Platform"] + [handle for (_, handle), _ in ordered],
             ["Display"] + [inp for (inp, _), _ in ordered]]
    for label, col in zip(labels, columns):
        table.append([label] + [" / ".join(_symbol(c) for c in cells.get(col, [])) or "–"
                                for _, cells in ordered])
    lines = _table(table)
    legend = "✅ available · ❌ taken · ❓ unknown (check manually) · ⛔ not allowed on that platform"
    links = [r for r in results if r.get("reason") == "manual_only"]
    likely = any(r.get("reason") == "likely_free" for r in results)
    held = any((r.get("reason") or "").startswith("held_by:") for r in results)
    lines += ["", legend + (f" · {LIKELY} probably free" if likely else "")
              + (f" · {HELD} held by the Instagram account" if held else "")
              + (f" · {LINK} check yourself" if links else "")]
    if tlds:
        lines.append("Domain cells: name.tld / hyphenated-name.tld")
    manual = [r for r in results if r["status"] == "unknown" and r.get("reason") != "manual_only"]
    if manual:
        lines += ["", "Check manually:"]
        lines += [f"- {platforms[r['platform']]['name'] if not r['platform'].startswith('.') else r['platform']}"
                  f" `{r['handle']}` ({r['reason']}): {r['url']}" for r in manual]
    held_rows = [r for r in results if (r.get("reason") or "").startswith("held_by:")]
    if held_rows:
        lines += ["", f"{HELD} Held by an existing account (open it to see whose):"]
        for r in held_rows:
            holder = platforms[r["reason"].split(":", 1)[1]]
            lines.append(f"- {platforms[r['platform']]['name']} `{r['handle']}`: "
                         f"{holder['profile_url'].format(name=r['handle'])}")
    if links:
        lines += ["", f"{LINK} Check yourself (no automatic check possible):"]
        lines += [f"- {platforms[r['platform']]['name']}: {r['url']}" for r in links]
    hints = _hints(results, keys, platforms)
    if hints:
        lines += [""] + [f"> {h}" for h in hints]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="check.py",
        description="Check whether brand/project names are free on social platforms and domains.")
    ap.add_argument("names", nargs="*", help='names or handles, e.g. "Acme Studio" acmestudio.id')
    ap.add_argument("--mode", help="brand (default), project or all")
    ap.add_argument("--platforms", help="comma list; overrides --mode (e.g. ig,tiktok,youtube)")
    ap.add_argument("--skip", help="comma list of platforms to leave out")
    ap.add_argument("--tlds", help="comma list of domain extensions (default: com)")
    ap.add_argument("--no-domains", action="store_true", help="do not check domains")
    ap.add_argument("--variants", action="store_true",
                    help=f"also try common variants (separators, affixes), max {MAX_VARIANTS} per name")
    ap.add_argument("--country", help="country code for variant suffixes, e.g. id -> name.id, name_id")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-test", action="store_true", help="check every platform's canary names live")
    return ap


def _csv(value):
    return [v.strip().lstrip(".").lower() for v in value.split(",") if v.strip()] if value else None


def _entries(names: list, mode: str, use_variants: bool, country) -> list:
    entries = []
    for name in names:
        tokens = tokenize(name)
        handle = to_handle(name)
        if not handle:
            raise ValueError(f"{name!r} has no letters or digits")
        labels = ["".join(tokens)] + (["-".join(tokens)] if len(tokens) > 1 else [])
        handles = variants(tokens, mode, country) if use_variants else [handle]
        if use_variants and handle not in handles:
            handles = [handle] + handles[: MAX_VARIANTS - 1]
        for i, h in enumerate(handles):
            entries.append({"input": name, "handle": h, "labels": labels if i == 0 else []})
    return entries


def main(argv=None) -> int:
    ap = _parser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    platforms = load_platforms()
    if args.self_test:
        return run_self_test(platforms, as_json=args.json)
    if not args.names:
        ap.print_usage(sys.stderr)
        print("check.py: error: give at least one name", file=sys.stderr)
        return 2
    cfg = load_config()
    mode = args.mode or cfg.get("mode") or "brand"
    try:
        keys = select_platforms(platforms, mode, _csv(args.platforms) or cfg.get("platforms"),
                                _csv(args.skip) or cfg.get("skip") or [])
        tlds = [] if args.no_domains else (_csv(args.tlds) or [t.lstrip(".").lower() for t in cfg.get("tlds", [])]
                                           or ["com"])
        country = (args.country or cfg.get("country") or "").strip().lstrip(".").lower() or None
        entries = _entries(args.names, mode, args.variants, country)
    except ValueError as e:
        print(f"check.py: error: {e}", file=sys.stderr)
        return 2
    results = run(entries, keys, tlds, platforms)
    if args.json:
        print(json.dumps({"results": results, "hints": _hints(results, keys, platforms)},
                         indent=2, ensure_ascii=False))
    else:
        print(render_markdown(results, keys, tlds, platforms))
    return 0


def self_test(platforms: dict, fetch=fetch, sleep=time.sleep) -> list:
    """Check each platform's canary pair live: does taken still read taken, and free read free?"""
    report = []
    for key, p in platforms.items():
        if p["check"]["type"] in ("manual_only", "same_as"):
            report.append({"platform": key, "state": "skipped", "detail": p["check"]["type"]})
            continue
        taken_name, free_name = p["canary"]["taken"], p["canary"]["available"]
        res = check_platform(key, platforms, [taken_name, free_name], fetch, sleep)
        t, a = res[taken_name], res[free_name]
        detail = f"{taken_name}: {t['status']} ({t['reason']}), {free_name}: {a['status']} ({a['reason']})"
        reasons = {t["reason"] or "", a["reason"] or ""}
        if reasons & {"blocked", "rate_limited", "network_error", "sandbox_blocked", "login_wall"}:
            state = "blocked"
        elif t["status"] == "taken" and (a["status"] == "available" or a["reason"] == "likely_free"):
            state = "ok"
        else:
            state = "broken"
        report.append({"platform": key, "state": state, "detail": detail})
    return report


def run_self_test(platforms: dict, as_json: bool = False) -> int:
    report = self_test(platforms, fetch, time.sleep)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print("| Platform | State | Detail |\n|---|---|---|")
        for r in report:
            print(f"| {r['platform']} | {r['state']} | {r['detail']} |")
    return 1 if any(r["state"] == "broken" for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
