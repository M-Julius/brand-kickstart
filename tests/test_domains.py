import json
import unittest

from _load import check

BOOT = {"services": [[["com", "net"], ["https://rdap.verisign.com/com/v1/"]],
                     [["id"], ["https://rdap.pandi.id/rdap/"]]]}


def fake_fetch(table):
    """table: url -> Response; unknown URLs are a network error."""
    calls = []

    def fetch(url, **kw):
        calls.append(url)
        return table.get(url, check.Response(0, "no route", url))

    fetch.calls = calls
    return fetch


def R(status, body=""):
    return check.Response(status, body, "https://rdap.test/")


def no_whois(server, query):
    raise OSError("whois unreachable")


def fake_whois(bodies):
    """bodies: query -> WHOIS text. Server lookups at IANA answer with whois.test."""
    calls = []

    def whois(server, query):
        calls.append((server, query))
        if server == "whois.iana.org":
            return "refer:        whois.test\nwhois:        whois.test\n"
        return bodies[query]

    whois.calls = calls
    return whois


class DomainsTest(unittest.TestCase):
    def test_bootstrap_parse(self):
        f = fake_fetch({check.IANA_BOOTSTRAP: R(200, json.dumps(BOOT))})
        self.assertEqual(check.load_bootstrap(f), {
            "com": "https://rdap.verisign.com/com/v1/",
            "net": "https://rdap.verisign.com/com/v1/",
            "id": "https://rdap.pandi.id/rdap/",
        })

    def test_bootstrap_failure_returns_none(self):
        self.assertIsNone(check.load_bootstrap(fake_fetch({})))
        bad = fake_fetch({check.IANA_BOOTSTRAP: R(200, "not json")})
        self.assertIsNone(check.load_bootstrap(bad))

    def test_domain_taken_and_free(self):
        boot = {"com": "https://rdap.verisign.com/com/v1/"}
        f = fake_fetch({
            "https://rdap.verisign.com/com/v1/domain/google.com": R(200, '{"ldhName":"GOOGLE.COM"}'),
            "https://rdap.verisign.com/com/v1/domain/acmestudio.com": R(404),
        })
        taken = check.check_domain("google", "com", boot, f, whois=no_whois)
        free = check.check_domain("acmestudio", "com", boot, f, whois=no_whois)
        self.assertEqual((taken["status"], taken["platform"], taken["handle"]), ("taken", ".com", "google.com"))
        self.assertEqual(free["status"], "available")
        self.assertEqual(free["url"], "https://www.whois.com/whois/acmestudio.com")

    def test_tld_without_rdap(self):
        f = fake_fetch({})
        r = check.check_domain("acmestudio", "zz", {"com": "https://x/"}, f, whois=no_whois)
        self.assertEqual((r["status"], r["reason"]), ("unknown", "no_rdap"))
        self.assertEqual(f.calls, [])

    def test_bootstrap_failure(self):
        r = check.check_domain("acmestudio", "com", None, fake_fetch({}), whois=no_whois)
        self.assertEqual((r["status"], r["reason"]), ("unknown", "network_error"))

    def test_domain_rate_limit(self):
        boot = {"com": "https://rdap.verisign.com/com/v1"}  # no trailing slash on purpose
        f = fake_fetch({"https://rdap.verisign.com/com/v1/domain/acmestudio.com": R(429)})
        r = check.check_domain("acmestudio", "com", boot, f, whois=no_whois)
        self.assertEqual((r["status"], r["reason"]), ("unknown", "rate_limited"))


class WhoisTest(unittest.TestCase):
    def setUp(self):
        check._WHOIS_SERVERS.clear()

    def test_classify_whois_bodies(self):
        cases = [
            ("detik.id", "Domain Name: DETIK.ID\nRegistry Domain ID: 1", "taken"),
            ("x.id", "The queried object does not exist: DOMAIN NOT FOUND", "available"),
            ("x.io", "Domain not found.\nTerms of Use: ...", "available"),
            ("x.us", "No Data Found", "available"),
            ("x.com", 'No match for "X.COM".', "available"),
            ("google.de", "Domain: google.de\nStatus: connect", "taken"),
            ("x.de", "Domain: x.de\nStatus: free", "available"),
            ("x.my", ">>> Domain x.my is available for registration", "available"),
            ("x.jp", "No match!!", "available"),
            ("google.jp", "[Domain Name]                   GOOGLE.JP", "taken"),
            ("x.zz", "Rate limit exceeded", None),
        ]
        for domain, body, want in cases:
            with self.subTest(domain=domain):
                self.assertEqual(check.classify_whois(domain, body), want)

    def test_no_rdap_falls_back_to_whois(self):
        w = fake_whois({"acmestudio.io": "Domain not found.", "github.io": "Domain Name: github.io"})
        free = check.check_domain("acmestudio", "io", {"com": "https://x/"}, fake_fetch({}), whois=w)
        taken = check.check_domain("github", "io", {"com": "https://x/"}, fake_fetch({}), whois=w)
        self.assertEqual((free["status"], free["reason"]), ("available", None))
        self.assertEqual(taken["status"], "taken")
        self.assertEqual([c for c in w.calls if c[0] == "whois.iana.org"], [("whois.iana.org", "io")])  # cached

    def test_rdap_network_error_falls_back_to_whois(self):
        w = fake_whois({"acmestudio.id": "DOMAIN NOT FOUND"})
        r = check.check_domain("acmestudio", "id", {"id": "https://rdap.down/"}, fake_fetch({}), whois=w)
        self.assertEqual(r["status"], "available")

    def test_second_level_tld_asks_iana_for_last_label(self):
        w = fake_whois({"acmestudio.co.id": "DOMAIN NOT FOUND"})
        r = check.check_domain("acmestudio", "co.id", {"id": "https://rdap.down/"}, fake_fetch({}), whois=w)
        self.assertEqual(r["status"], "available")
        self.assertIn(("whois.iana.org", "id"), w.calls)

    def test_jprs_gets_english_suffix(self):
        def w(server, query):
            if server == "whois.iana.org":
                return "whois:        whois.jprs.jp\n"
            self.assertEqual(query, "acmestudio.jp/e")
            return "No match!!"
        r = check.check_domain("acmestudio", "jp", {}, fake_fetch({}), whois=w)
        self.assertEqual(r["status"], "available")

    def test_whois_unclear_stays_unknown(self):
        w = fake_whois({"acmestudio.io": "Rate limit exceeded"})
        r = check.check_domain("acmestudio", "io", {}, fake_fetch({}), whois=w)
        self.assertEqual((r["status"], r["reason"]), ("unknown", "no_rdap"))


if __name__ == "__main__":
    unittest.main()
