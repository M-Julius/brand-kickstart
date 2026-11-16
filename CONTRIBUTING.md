# Contributing

Thanks for helping. Most contributions are adding a platform, fixing one that changed, or adding styles to the brand kit. Platform work usually means editing a single JSON entry.

## Repository layout

```
skills/brand-kickstart/        the skill: copy this folder and it works
  SKILL.md                     the agent's instructions
  scripts/check.py             name checks (standard library only)
  scripts/platforms.json       one entry per platform
  scripts/brand.py             brand kit renderer (resvg-py)
  references/brand-kit.md      logo, illustration and asset flow
  references/styles.md         typefaces, palettes, mark types, layouts
.claude-plugin/                Claude Code plugin and marketplace manifests
docs/demo/                     README demos, rebuilt by docs/demo/build.py
tests/                         unittest, no network
```

## Ground rules

These keep the tool honest, light and safe to publish:

1. **`unknown` beats a guess.** A check must have a positive signal for *taken* and a positive signal for *available*. If neither appears, the result is `unknown`. Never fall back to "taken" because a page loaded.
2. **No login, cookies, API keys, CAPTCHA or Cloudflare bypassing, and no browser automation.** If a platform cannot be checked without those, add it as `manual_only`.
3. **Standard library only** in `check.py`, with no exceptions. `brand.py` may use `resvg-py`, and nothing else.
4. **Be gentle.** Keep `min_interval` at 0.3 s or more. Use 1.0 s for platforms that rate-limit.

## Setup

```bash
git clone https://github.com/M-Julius/brand-kickstart.git
cd brand-kickstart
python3 -m unittest discover -s tests -v                 # offline, stdlib only
python3 -m venv .venv && .venv/bin/pip install resvg-py  # only for brand kit and demo work
```

## Adding a platform

1. **Find a request that answers differently for a taken name and a free name.** Use a long random string (e.g. `zqxv8k2brnd`) as the free name. Good signals, best first:
   - an official "username available" endpoint (like X's)
   - an HTTP status (404 for free)
   - a stable marker in the page (like Instagram's `"pageID"`)
2. **Add an entry to `skills/brand-kickstart/scripts/platforms.json`:**

   ```json
   "example": {
     "name": "Example",
     "url": "https://example.com/api/users/{name}",
     "profile_url": "https://example.com/{name}",
     "check": { "type": "status", "taken": [200], "available": [404] },
     "rule": { "pattern": "^[a-z0-9_]{3,30}$" },
     "modes": ["brand"],
     "canary": { "taken": "a-name-that-surely-exists", "available": "zqxv8k2brnd" }
   }
   ```

   | Field | Meaning |
   |---|---|
   | `url` | What the checker requests. `{name}` is the lowercase handle. |
   | `profile_url` | What the user clicks. |
   | `check.type` | `status` (by HTTP status), `json` (`field` value in `taken` / `available` / optional `invalid` lists), `body` (`taken_regex` / `available_regex`, optional `blocked_regex`), `same_as` (`platform`: copy another platform's result), `manual_only` (no request, always a link). |
   | `rule.pattern` | The platform's own username rule, written lowercase. Names that break it are shown ⛔ and never requested. |
   | `modes` | Any of `brand`, `project`. |
   | `canary` | One taken and one free name, used by tests and `--self-test`. |
   | `min_interval` | Optional. Seconds between requests (default 0.3). |
   | `user_agent` | Optional. `"plain"` sends an honest `brand-kickstart/…` User-Agent instead of a browser one. Instagram and Facebook need it: they serve an error page to a client that claims to be Chrome but does not look like Chrome. |
   | `timeout` | Optional. Seconds per request (default 10), for slow, heavy pages. |
   | `held_by` | Optional. The platform whose account holds this handle, e.g. `"instagram"` for Threads. A free result here becomes 🔒 (`held_by:<platform>`) when that account exists. |
   | `hosts` | Optional. Other hosts the platform may redirect to, e.g. `["web.facebook.com"]`. A redirect to any other host is treated as blocked. |
   | `check.available_unconfirmed` | Optional. `true` if the "free" page also shows for names that exist but are hidden. The result becomes ✅? (`likely_free`), never ✅. |
   | `preflight` | Optional. `true` to check the taken canary before each run and stop early if this IP is blocked. |

3. **Verify against real names:**

   ```bash
   python3 -I tests/capture_fixtures.py example
   ```

   It checks the canary pair plus random free names, and prints `BAD` for any mismatch. Add more known-taken names to `EXTRA_TAKEN` in that script. It also saves `tests/fixtures/example_taken.*` and `example_free.*`.
4. **Run the tests:** `python3 -m unittest discover -s tests -v`. `test_fixtures_classify` and the self-test tests pick up the new fixtures automatically.
5. **Open a PR.** Include the `capture_fixtures.py` output.

## Fixing a broken platform

The weekly canary workflow opens a **"platform broken: …"** issue when `--self-test` fails.

1. Run `python3 skills/brand-kickstart/scripts/check.py --self-test` to reproduce.
2. Run `python3 -I tests/capture_fixtures.py <platform> --raw-dir /tmp/raw`. Compare the taken and free bodies in `/tmp/raw` to find the new signal.
3. Update the entry. Recapture its fixtures with the same script. Run the tests. Open a PR that references the issue.

A platform reported as `blocked` in CI is not broken. Shared CI IPs get blocked often, so it is only a warning.

## Brand kit and styles

- **New font pairing or palette:** add a row to `references/styles.md`. Check that every font spec downloads:
  `python3 skills/brand-kickstart/scripts/brand.py fonts /tmp/f "Family:wght@400;700"`
- **New demo brand:** add `docs/demo/gallery/concepts/<id>/` with `logo.svg`, `illustration.svg` and `concept.json`. Use a made-up name, and draw everything from scratch: no emoji, clip-art or traced logos. Then rebuild:
  `python3 -m pip install resvg-py && brew install resvg && python3 docs/demo/build.py`
  (`brew install resvg` provides `usvg`; `cargo install usvg` works too.) Look at the PNGs before you open the PR.
  Commit only the sources and `docs/demo/preview/*.svg`; PNGs are ignored. A wordmark font that is not the concept's
  display or text face goes in `EXTRA_FONTS` in `build.py`.

## Code changes

`check.py` and `brand.py` are single files on purpose: the skill folder must stay copyable. Write a failing test first (`tests/test_*.py`, `unittest`, no network), then make it pass. Network calls go through the injected `fetch` or `render` function, so tests use fakes or fixtures.

## Releasing

1. Bump `version` in `.claude-plugin/plugin.json`.
2. Run `claude plugin validate .`.
3. Push a tag such as `v0.2.0`. The release workflow attaches `brand-kickstart.zip`, which is the file Claude.ai and ChatGPT users upload.
