"""
title: CSEEC Official Admissions
description: Read live public admissions evidence from allowlisted official university sites (Canada, Hong Kong, Singapore) without transmitting student data.
author: CSEEC
version: 0.3.0
license: MIT
"""

import asyncio
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import (
    build_opener,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
)
from urllib.robotparser import RobotFileParser

USER_AGENT = "CSEEC-Admissions-Reader/0.3 (+https://www.cseec.ca)"
# Also obey robots.txt rules aimed at user-triggered AI fetchers, since this tool is one.
ROBOT_AGENTS = (USER_AGENT, "ChatGPT-User", "Claude-User", "Claude-Web")
# Official Sectigo intermediate (from crt.sectigo.com) that admission.cuhk.edu.hk omits from its chain.
# Verification stays on; this only completes the chain to a system-trusted root.
EXTRA_INTERMEDIATES = """-----BEGIN CERTIFICATE-----
MIIGTDCCBDSgAwIBAgIQOXpmzCdWNi4NqofKbqvjsTANBgkqhkiG9w0BAQwFADBf
MQswCQYDVQQGEwJHQjEYMBYGA1UEChMPU2VjdGlnbyBMaW1pdGVkMTYwNAYDVQQD
Ey1TZWN0aWdvIFB1YmxpYyBTZXJ2ZXIgQXV0aGVudGljYXRpb24gUm9vdCBSNDYw
HhcNMjEwMzIyMDAwMDAwWhcNMzYwMzIxMjM1OTU5WjBgMQswCQYDVQQGEwJHQjEY
MBYGA1UEChMPU2VjdGlnbyBMaW1pdGVkMTcwNQYDVQQDEy5TZWN0aWdvIFB1Ymxp
YyBTZXJ2ZXIgQXV0aGVudGljYXRpb24gQ0EgRFYgUjM2MIIBojANBgkqhkiG9w0B
AQEFAAOCAY8AMIIBigKCAYEAljZf2HIz7+SPUPQCQObZYcrxLTHYdf1ZtMRe7Yeq
RPSwygz16qJ9cAWtWNTcuICc++p8Dct7zNGxCpqmEtqifO7NvuB5dEVexXn9RFFH
12Hm+NtPRQgXIFjx6MSJcNWuVO3XGE57L1mHlcQYj+g4hny90aFh2SCZCDEVkAja
EMMfYPKuCjHuuF+bzHFb/9gV8P9+ekcHENF2nR1efGWSKwnfG5RawlkaQDpRtZTm
M64TIsv/r7cyFO4nSjs1jLdXYdz5q3a4L0NoabZfbdxVb+CUEHfB0bpulZQtH1Rv
38e/lIdP7OTTIlZh6OYL6NhxP8So0/sht/4J9mqIGxRFc0/pC8suja+wcIUna0HB
pXKfXTKpzgis+zmXDL06ASJf5E4A2/m+Hp6b84sfPAwQ766rI65mh50S0Di9E3Pn
2WcaJc+PILsBmYpgtmgWTR9eV9otfKRUBfzHUHcVgarub/XluEpRlTtZudU5xbFN
xx/DgMrXLUAPaI60fZ6wA+PTAgMBAAGjggGBMIIBfTAfBgNVHSMEGDAWgBRWc1hk
lfmSGrASKgRieaFAFYghSTAdBgNVHQ4EFgQUaMASFhgOr872h6YyV6NGUV3LBycw
DgYDVR0PAQH/BAQDAgGGMBIGA1UdEwEB/wQIMAYBAf8CAQAwHQYDVR0lBBYwFAYI
KwYBBQUHAwEGCCsGAQUFBwMCMBsGA1UdIAQUMBIwBgYEVR0gADAIBgZngQwBAgEw
VAYDVR0fBE0wSzBJoEegRYZDaHR0cDovL2NybC5zZWN0aWdvLmNvbS9TZWN0aWdv
UHVibGljU2VydmVyQXV0aGVudGljYXRpb25Sb290UjQ2LmNybDCBhAYIKwYBBQUH
AQEEeDB2ME8GCCsGAQUFBzAChkNodHRwOi8vY3J0LnNlY3RpZ28uY29tL1NlY3Rp
Z29QdWJsaWNTZXJ2ZXJBdXRoZW50aWNhdGlvblJvb3RSNDYucDdjMCMGCCsGAQUF
BzABhhdodHRwOi8vb2NzcC5zZWN0aWdvLmNvbTANBgkqhkiG9w0BAQwFAAOCAgEA
YtOC9Fy+TqECFw40IospI92kLGgoSZGPOSQXMBqmsGWZUQ7rux7cj1du6d9rD6C8
ze1B2eQjkrGkIL/OF1s7vSmgYVafsRoZd/IHUrkoQvX8FZwUsmPu7amgBfaY3g+d
q1x0jNGKb6I6Bzdl6LgMD9qxp+3i7GQOnd9J8LFSietY6Z4jUBzVoOoz8iAU84OF
h2HhAuiPw1ai0VnY38RTI+8kepGWVfGxfBWzwH9uIjeooIeaosVFvE8cmYUB4TSH
5dUyD0jHct2+8ceKEtIoFU/FfHq/mDaVnvcDCZXtIgitdMFQdMZaVehmObyhRdDD
4NQCs0gaI9AAgFj4L9QtkARzhQLNyRf87Kln+YU0lgCGr9HLg3rGO8q+Y4ppLsOd
unQZ6ZxPNGIfOApbPVf5hCe58EZwiWdHIMn9lPP6+F404y8NNugbQixBber+x536
WrZhFZLjEkhp7fFXf9r32rNPfb74X/U90Bdy4lzp3+X1ukh1BuMxA/EEhDoTOS3l
7ABvc7BYSQubQ2490OcdkIzUh3ZwDrakMVrbaTxUM2p24N6dB+ns2zptWCva6jzW
r8IWKIMxzxLPv5Kt3ePKcUdvkBU/smqujSczTzzSjIoR5QqQA6lN1ZRSnuHIWCvh
JEltkYnTAH41QJ6SAWO66GrrUESwN/cgZzL4JLEqz1Y=
-----END CERTIFICATE-----
"""
TLS = ssl.create_default_context()
TLS.load_verify_locations(cadata=EXTRA_INTERMEDIATES)
_ROBOTS = {}

SOURCES = {
    "ubc": {
        "requirements": "https://you.ubc.ca/applying-ubc/requirements/canadian-high-schools/",
        "language": "https://you.ubc.ca/applying-ubc/requirements/english-language-competency/",
        "deadlines": "https://you.ubc.ca/applying-ubc/dates-deadlines/",
        "history": "https://pair.ubc.ca/student-data-analytics/enrolment/annual-enrolment-reports/",
    },
    "sfu": {
        "requirements": "https://www.sfu.ca/students/admission/admission-requirements/canadian-highschool/bc-yukon.html",
        "language": "https://www.sfu.ca/students/admission/admission-requirements.html",
        "deadlines": "https://www.sfu.ca/students/admission/apply/dates-deadlines.html",
        "history": "https://www.sfu.ca/students/admission/admission-requirements/historical-admission-grade-ranges.html",
    },
    # Canadian universities: requirement pages for Canadian / BC (Dogwood) applicants where the school has one.
    "utoronto": {
        "requirements": "https://future.utoronto.ca/requirements-canadian-students",
        "language": "https://future.utoronto.ca/english-language-requirements",
        "deadlines": "https://future.utoronto.ca/deadlines",
    },
    "uwaterloo": {
        "requirements": "https://uwaterloo.ca/future-students/admissions/admission-requirements",
        "language": "https://uwaterloo.ca/future-students/admissions/english-language-requirements",
        "deadlines": "https://uwaterloo.ca/future-students/admissions/deadlines",
        "history": "https://uwaterloo.ca/future-students/admissions/admission-average",
    },
    "western": {
        "requirements": "https://welcome.uwo.ca/next-steps/requirements/canadian-high-school/british-columbia-yukon.html",
        "language": "https://welcome.uwo.ca/next-steps/requirements/english-language-proficiency.html",
        "deadlines": "https://welcome.uwo.ca/next-steps/apply/admission-deadlines.html",
    },
    "mcgill": {
        "requirements": "https://www.mcgill.ca/undergraduate-admissions/apply/requirements/canadian",
        "language": "https://www.mcgill.ca/undergraduate-admissions/apply/english-proficiency",
        "deadlines": "https://www.mcgill.ca/undergraduate-admissions/apply/admission-decision-dates",
    },
    "queens": {
        "requirements": "https://www.queensu.ca/admission/applying/admission-requirements",
        "language": "https://www.queensu.ca/admission/applicants/english-proficiency",
        "deadlines": "https://www.queensu.ca/admission/applying/dates-deadlines",
        "history": "https://www.queensu.ca/admission/applying/competitive-average",
    },
    "ucalgary": {
        "requirements": "https://www.ucalgary.ca/future-students/undergraduate/admissions/requirements",
        "language": "https://www.ucalgary.ca/future-students/undergraduate/admissions/how-to-apply/english-language-requirements",
        "deadlines": "https://www.ucalgary.ca/future-students/undergraduate/admissions/dates",
    },
    "uottawa": {
        "requirements": "https://www.uottawa.ca/etudes/etudes-premier-cycle/prealables-programmes",
        "language": "https://www.uottawa.ca/study/undergraduate-studies/language-requirements",
        "deadlines": "https://www.uottawa.ca/study/undergraduate-studies/application-deadlines",
    },
    "yorku": {
        "requirements": "https://futurestudents.yorku.ca/your-application/how-apply/canadian-high-school-student-outside-ontario",
        "language": "https://futurestudents.yorku.ca/requirements/language-tests",
        "deadlines": "https://futurestudents.yorku.ca/requirements/deadlines",
    },
    "tmu": {
        "requirements": "https://www.torontomu.ca/admissions/undergraduate/requirements/canadian/british-columbia/",
        "language": "https://www.torontomu.ca/admissions/undergraduate/requirements/english-language/",
        "deadlines": "https://www.torontomu.ca/admissions/undergraduate/apply/application-dates/",
    },
    "hku": {
        "requirements": "https://admissions.hku.hk/apply/international-qualifications",
        "language": "https://admissions.hku.hk/apply/international-qualifications/english-language-requirement",
    },
    "cuhk": {
        "requirements": "https://admission.cuhk.edu.hk/application/overseas-other-qualifications-non-local-international-team/requirements/",
        "deadlines": "https://admission.cuhk.edu.hk/application/overseas-other-qualifications-non-local-international-team/important-dates/",
    },
    "hkust": {
        "requirements": "https://join.hkust.edu.hk/admissions/international-qualifications",
    },
    "ntu": {
        "requirements": "https://www.ntu.edu.sg/admissions/undergraduate/admissions/general-admission-requirements/international-qualifications/canada-qualifications",
        "deadlines": "https://www.ntu.edu.sg/admissions/undergraduate/important-links/important-dates",
    },
    # NUS School of Computing pages (official NUS); the university-wide OAM site sits behind a bot challenge.
    "nus": {
        "requirements": "https://www.comp.nus.edu.sg/admissions/faq/",
        "deadlines": "https://www.comp.nus.edu.sg/admissions/",
    },
}
SCOPE_NOTES = {
    "nus": "Only NUS School of Computing pages are readable; university-wide international-qualification requirements and the IGP are on nus.edu.sg/oam and need manual checking.",
}
# Third-party pages (not the university's own site). Results are always labelled unofficial.
UNOFFICIAL = {
    "ualberta": {
        "requirements": [("https://alis.alberta.ca/occinfo/post-secondary-programs/bachelor-of-science/university-of-alberta/8405e09d-1e5e-4b8c-b2fa-a12700c5f2fe/",
                          "Government of Alberta – alis program listing (Alberta curriculum course names)")],
    },
    "nus": {
        "history": [("https://sgschoolscop.com/university-indicative-grade-profiles-ign/",
                     "SG Education Portal – copy of NUS/NTU/SMU A-Level IGP (third-party)")],
    },
}
UNOFFICIAL_LABEL = "非官方来源，仅供参考 / Unofficial source, for reference only"
# Official sites this reader must not read automatically (bot challenge or robots.txt opt-out); the model must say so.
UNSUPPORTED = {
    "mcmaster": ("https://future.mcmaster.ca/apply/requirements/", "official robots.txt opts out of AI agents"),
    "ualberta": ("https://www.ualberta.ca/en/admissions/undergraduate/index.html", "official site and calendar sit behind a bot challenge"),
}
PREFIXES = {
    "ubc": {
        "you.ubc.ca": ("/applying-ubc/", "/ubc_programs/"),
        "pair.ubc.ca": ("/student-data-analytics/",),
        "pair.ok.ubc.ca": ("/wp-content/uploads/",),
    },
    "sfu": {"www.sfu.ca": ("/students/admission/",)},
    "utoronto": {"future.utoronto.ca": ("/",)},
    "uwaterloo": {"uwaterloo.ca": ("/future-students/",)},
    "western": {"welcome.uwo.ca": ("/next-steps/",)},
    "cuhk": {"admission.cuhk.edu.hk": ("/application/overseas-other-qualifications-non-local-international-team/",)},
    "mcgill": {"www.mcgill.ca": ("/undergraduate-admissions/",)},
    "queens": {"www.queensu.ca": ("/admission/",)},
    "ucalgary": {"www.ucalgary.ca": ("/future-students/undergraduate/",)},
    "uottawa": {"www.uottawa.ca": ("/study/undergraduate-studies/", "/etudes/etudes-premier-cycle/")},
    "yorku": {"futurestudents.yorku.ca": ("/requirements", "/your-application/", "/program/")},
    "tmu": {"www.torontomu.ca": ("/admissions/undergraduate/", "/programs/undergraduate/")},
    "hku": {"admissions.hku.hk": ("/apply/", "/programmes/")},
    "hkust": {"join.hkust.edu.hk": ("/admissions/", "/programs/")},
    "ntu": {"www.ntu.edu.sg": ("/admissions/undergraduate/",)},
    "nus": {"www.comp.nus.edu.sg": ("/admissions/",)},
    "unofficial": {"alis.alberta.ca": ("/occinfo/post-secondary-programs/",), "sgschoolscop.com": ("/university-indicative-grade-profiles",)},
}
INSTITUTIONS = Literal[
    "ubc", "sfu", "utoronto", "uwaterloo", "mcmaster", "mcgill", "queens", "western",
    "ualberta", "ucalgary", "uottawa", "yorku", "tmu", "hku", "cuhk", "hkust", "nus", "ntu",
]
PROGRAM_WORDS = {
    "general": (),
    "engineering": ("engineering", "applied-science"),
    "computing": ("computing", "computer", "software"),
    "business": ("business", "commerce", "beedie"),
    "science": ("science",),
    "arts": ("arts", "humanities", "social-science"),
}
LIMIT = 6 * 1024 * 1024
ROBOTS_TIMEOUT = 5
PAGE_TIMEOUT = 8
ROBOTS_TTL = 24 * 3600
# Official admissions pages change a few times a year; reuse a successful read for a day.
RESULT_TTL = 24 * 3600
CACHE_DIR = "/app/backend/data/cache/cseec_admissions"
BATCH_LIMIT = 6
# One lock per host: different universities are read in parallel, one site is never hit concurrently.
_HOST_LOCKS = {}
_HOST_LOCKS_GUARD = threading.Lock()
_RESULTS = {}


def host_lock(hostname):
    with _HOST_LOCKS_GUARD:
        return _HOST_LOCKS.setdefault(hostname, threading.Lock())


def cache_path(key):
    return os.path.join(CACHE_DIR, key.replace(":", "__") + ".json")


def cached_result(key):
    """Return (stored_at, result) from memory or disk if younger than RESULT_TTL."""
    entry = _RESULTS.get(key)
    if not entry:
        try:
            with open(cache_path(key), encoding="utf-8") as handle:
                entry = tuple(json.load(handle))
            _RESULTS[key] = entry
        except (OSError, ValueError, TypeError):
            return None
    if time.time() - entry[0] > RESULT_TTL:
        return None
    return entry


def store_result(key, result):
    entry = (time.time(), result)
    _RESULTS[key] = entry
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        temporary = cache_path(key) + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(entry, handle, ensure_ascii=False)
        os.replace(temporary, cache_path(key))
    except OSError:
        pass


def validate_url(url, institution, resolve=True):
    """Reject query strings, credentials, non-official routes and non-public DNS."""
    parts = urlsplit(url)
    prefixes = PREFIXES[institution].get(parts.hostname, ())
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.query
        or parts.fragment
        or not any(parts.path.startswith(p) for p in prefixes)
        or "%" in parts.path
        or ".." in parts.path
        or "\\" in parts.path
    ):
        raise ValueError("URL outside approved public admissions routes")
    if resolve:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(a[4][0]).is_global for a in addresses
        ):
            raise ValueError("Non-public destination blocked")
    return url


class CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, institution):
        self.institution = institution
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 3:
            raise ValueError("Redirect limit reached")
        validate_url(newurl, self.institution)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.title = []
        self.text = []
        self.links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.anchor = [attrs.get("href") or "", ""]
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text.append("\n")
        if tag in ("td", "th"):
            self.text.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor is not None:
            self.links.append(tuple(self.anchor))
            self.anchor = None
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        else:
            self.text.append(data)
        if self.anchor is not None:
            self.anchor[1] += data

    def visible_text(self):
        text = "\n".join(
            line
            for part in "".join(self.text).splitlines()
            if (line := " ".join(part.split()))
        )
        if len(re.sub(r"[\s|]", "", text)) < 300 and getattr(self, "raw", ""):
            # Malformed script/noscript nesting can leave the parser skipping the body; strip tags instead.
            raw = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1\s*>", " ", self.raw)
            raw = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", "\n", raw)
            raw = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
            text = "\n".join(line for part in raw.splitlines() if (line := " ".join(part.split())))
        return text


def robots_allowed(url):
    """Honour the site's robots.txt for this tool and for user-triggered AI fetchers (cached 24 hours)."""
    parts = urlsplit(url)
    cached = _ROBOTS.get(parts.hostname)
    if not cached or time.time() - cached[0] > ROBOTS_TTL:
        parser = RobotFileParser()
        try:
            opener = build_opener(ProxyHandler({}), HTTPSHandler(context=TLS))
            with opener.open(
                Request(f"https://{parts.hostname}/robots.txt", headers={"User-Agent": USER_AGENT}),
                timeout=ROBOTS_TIMEOUT,
            ) as response:
                parser.parse(response.read(512 * 1024).decode("utf-8", errors="replace").splitlines())
        except Exception as error:
            # A missing robots.txt allows reading; any other failure is treated as "do not read".
            if getattr(error, "code", None) in (404, 410):
                parser.parse([])
            else:
                parser.parse(["User-agent: *", "Disallow: /"])
        cached = _ROBOTS[parts.hostname] = (time.time(), parser)
    return all(cached[1].can_fetch(agent, url) for agent in ROBOT_AGENTS)


def fetch_page(url, institution):
    lock = host_lock(urlsplit(url).hostname)
    if not lock.acquire(timeout=30):
        raise TimeoutError("Another read of this site is still running")
    try:
        return read_page(url, institution)
    finally:
        lock.release()


def read_page(url, institution):
    validate_url(url, institution)
    if not robots_allowed(url):
        raise PermissionError("robots.txt disallows automated reading")
    opener = build_opener(
        ProxyHandler({}), HTTPSHandler(context=TLS), CheckedRedirect(institution)
    )
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Encoding": "identity",
        },
    )
    with opener.open(request, timeout=PAGE_TIMEOUT) as response:
        validate_url(response.url, institution)
        mime = response.headers.get_content_type()
        if mime != "text/html":
            raise ValueError("HTML reader cannot verify PDF/dynamic document contents")
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Response exceeds 6 MiB")
        parser = Page()
        parser.raw = raw.decode(
            response.headers.get_content_charset() or "utf-8", errors="replace"
        )
        parser.feed(parser.raw)
        return parser, response.url


def excerpts(text, keywords, maximum=5000):
    """Keep source order and headings; output is an excerpt, never a full-coverage claim."""
    lines = text.splitlines()
    chosen = set()
    terms = tuple(keywords) + (
        "admission",
        "requirement",
        "deadline",
        "minimum",
        "past three",
        "guarantee",
        "enrolment",
        "enrollment",
        "grade",
        "report",
        "202",
        "british columbia",
        "canadian",
        "advanced placement",
        "average",
        "english",
    )
    for index, line in enumerate(lines):
        if any(word in line.lower() for word in terms):
            chosen.update(range(max(0, index - 2), min(len(lines), index + 9)))
    result = "\n".join(lines[i] for i in sorted(chosen)) or text
    return result[:maximum], len(result) > maximum


def collect(institution, topic, program, entry_year):
    if institution in UNSUPPORTED:
        url, reason = UNSUPPORTED[institution]
        return {
            "status": "official_site_not_readable",
            "institution": institution,
            "official_site": url,
            "reason": reason,
            "instruction": "官网未查到，需人工核实。Do not state any numbers for this university.",
        }
    if (
        institution not in SOURCES
        or topic not in ("requirements", "language", "deadlines", "history")
        or program not in PROGRAM_WORDS
    ):
        raise ValueError(
            "Use supported public identifiers only; no student data or free text"
        )
    if type(entry_year) is not int or not 2020 <= entry_year <= 2100:
        raise ValueError("entry_year must be an integer from 2020 to 2100")
    if topic not in SOURCES[institution]:
        return {
            "status": "topic_not_available",
            "institution": institution,
            "topic": topic,
            "available_topics": list(SOURCES[institution]),
            "instruction": "官网未查到，需人工核实。No official page for this topic is configured; do not state numbers for it.",
        }
    key = f"{institution}:{topic}:{program}"
    hit = cached_result(key)
    if hit:
        result = dict(hit[1])
        result["requested_entry_year"] = entry_year
        result["cached_read"] = {
            "read_minutes_ago": int((time.time() - hit[0]) / 60),
            "note": "Reused an official-page read from the last 24 hours; retrieved_at_utc shows when each page was read.",
        }
        return result
    result = {
        "status": "partial_evidence",
        "institution": institution,
        "topic": topic,
        "program_direction": program,
        "requested_entry_year": entry_year,
        "entry_year_verified": False,
        "sources": [],
        "failures": [],
        "limitations": [
            "Evidence excerpts, not verified eligibility or complete requirements.",
            "Requirement pages target Canadian/BC applicants where available; offshore BC Dogwood eligibility still needs counsellor confirmation.",
            "Observed years are not verified applicable admission cycles.",
            "No student data accepted; no external AI or paid search API used.",
        ] + ([SCOPE_NOTES[institution]] if institution in SCOPE_NOTES else []),
    }
    pending = [SOURCES[institution][topic]]
    for index in range(3):
        if index >= len(pending):
            break
        url = pending[index]
        try:
            page, final_url = fetch_page(url, institution)
            text = page.visible_text()
            evidence, truncated = excerpts(text, PROGRAM_WORDS[program])
            if len(text) < 100:
                raise ValueError(
                    "Insufficient readable content; manual verification required"
                )
            links = []
            documents = []
            for href, label in page.links:
                candidate = urljoin(final_url, href.strip())
                parts = urlsplit(candidate)
                candidate = urlunsplit(parts._replace(fragment=""))
                try:
                    validate_url(candidate, institution, resolve=False)
                except ValueError:
                    continue
                if parts.path.lower().endswith(".pdf"):
                    if candidate not in {v["url"] for v in documents}:
                        documents.append(
                            {
                                "url": candidate,
                                "title": " ".join(label.split())[:160],
                                "content_verified": False,
                                "status": "PDF_reader_required",
                            }
                        )
                elif candidate not in {v["url"] for v in links}:
                    links.append(
                        {"url": candidate, "title": " ".join(label.split())[:160]}
                    )
            result["sources"].append(
                {
                    "url": final_url,
                    "title": "".join(page.title).strip(),
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source_year_mentions": sorted(
                        set(re.findall(r"\b20\d{2}\b", text))
                    ),
                    "applicable_entry_year": None,
                    "requires_counsellor_verification": True,
                    "excerpt": evidence,
                    "excerpt_truncated": truncated,
                    "discovered_links": links[:15],
                    "unread_official_documents": documents[:10],
                }
            )
            if index == 0 and program != "general":
                ranked = [
                    link
                    for link in links
                    if any(
                        word in (link["title"] + " " + link["url"]).lower()
                        for word in PROGRAM_WORDS[program]
                    )
                ]
                pending.extend(
                    link["url"] for link in ranked if link["url"] not in pending
                )
                pending = pending[:3]
        except Exception as error:
            # Return exception type only: do not include request or confidential runtime state.
            result["failures"].append(
                {
                    "url": url,
                    "reason": type(error).__name__,
                    "status": "manual_verification_required",
                }
            )
    if not result["sources"]:
        result["status"] = "fetch_failed"
        result["instruction"] = "官网未查到，需人工核实。The official page could not be fetched now; do not state numbers."
    elif not result["failures"]:
        # Only complete reads are reused; partial or failed reads are retried next time.
        store_result(key, result)
    return result


def collect_unofficial(institution, topic):
    pages = UNOFFICIAL.get(institution, {}).get(topic)
    if not pages:
        return {
            "status": "no_unofficial_source",
            "institution": institution,
            "topic": topic,
            "available": {k: list(v) for k, v in UNOFFICIAL.items()},
            "instruction": "官网未查到，需人工核实。No vetted third-party page for this; do not state numbers.",
        }
    result = {"status": "unofficial_evidence", "source_type": "unofficial", "label": UNOFFICIAL_LABEL,
              "institution": institution, "topic": topic, "sources": [], "failures": [],
              "rules": ["Quote only with the label above, the link and the fetch date, in a separate note.",
                        "Never present this as the university's official requirement.",
                        "If the page's admission year is unclear or older than the current cycle, say so."]}
    for url, publisher in pages:
        try:
            page, final_url = fetch_page(url, "unofficial")
            text = page.visible_text()
            evidence, truncated = excerpts(text, ())
            result["sources"].append({
                "url": final_url, "publisher": publisher, "source_type": "unofficial", "label": UNOFFICIAL_LABEL,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_year_mentions": sorted(set(re.findall(r"\b20\d{2}\b", text))),
                "excerpt": evidence, "excerpt_truncated": truncated,
            })
        except Exception as error:
            result["failures"].append({"url": url, "reason": type(error).__name__})
    if not result["sources"]:
        result["status"] = "fetch_failed"
        result["instruction"] = "官网未查到，需人工核实。"
    return result


class Tools:
    async def list_official_admissions_sources(self) -> str:
        """List supported official source IDs. Does not access the network."""
        return json.dumps(
            {
                "institutions": {k: list(v) for k, v in SOURCES.items()},
                "not_readable": {k: v[1] for k, v in UNSUPPORTED.items()},
                "unofficial_sources": {k: list(v) for k, v in UNOFFICIAL.items()},
                "program_directions": list(PROGRAM_WORDS),
                "scope": "Official HTML pages only (live read, reused for up to 24 hours); not PDFs or universities outside this list.",
            },
            ensure_ascii=False,
        )

    async def get_official_admissions(
        self,
        institution: INSTITUTIONS,
        topic: Literal["requirements", "language", "deadlines", "history"],
        program: Literal[
            "general", "engineering", "computing", "business", "science", "arts"
        ],
        entry_year: int,
    ) -> str:
        """Read live official admissions evidence. Public IDs only; never student data.

        :param institution: University ID (ubc, sfu, utoronto, uwaterloo, mcmaster, mcgill, queens, western, ualberta, ucalgary, uottawa, yorku, tmu, hku, cuhk, hkust, nus, ntu); no URLs or student details.
        :param topic: Evidence type; use history for past admissions data.
        :param program: Public program direction for bounded official link discovery.
        :param entry_year: Target entry year, not an assertion about source validity.
        """
        try:
            data = await asyncio.to_thread(
                collect, institution, topic, program, entry_year
            )
        except (ValueError, TypeError):
            data = {
                "status": "invalid_public_identifier",
                "message": "Use supported IDs and integer year only",
            }
        return json.dumps(data, ensure_ascii=False)

    async def get_official_admissions_batch(
        self,
        institutions: list[INSTITUTIONS],
        topic: Literal["requirements", "language", "deadlines", "history"],
        program: Literal[
            "general", "engineering", "computing", "business", "science", "arts"
        ],
        entry_year: int,
    ) -> str:
        """Read official admissions evidence for several universities at once (up to 6), in parallel. Prefer this over repeated single calls when comparing universities. Public IDs only; never student data.

        :param institutions: University IDs, e.g. ["ubc", "sfu", "uwaterloo"]; no URLs or student details.
        :param topic: Evidence type; use history for past admissions data.
        :param program: Public program direction for bounded official link discovery.
        :param entry_year: Target entry year, not an assertion about source validity.
        """
        if not isinstance(institutions, list) or not institutions:
            return json.dumps({"status": "invalid_public_identifier"}, ensure_ascii=False)
        chosen = list(dict.fromkeys(institutions))[:BATCH_LIMIT]

        async def one(institution):
            try:
                return await asyncio.to_thread(
                    collect, institution, topic, program, entry_year
                )
            except (ValueError, TypeError, KeyError):
                return {"status": "invalid_public_identifier", "institution": institution}

        results = await asyncio.gather(*(one(i) for i in chosen))
        data = {"results": results}
        if len(institutions) > len(chosen):
            data["skipped"] = institutions[len(chosen):]
            data["note"] = f"At most {BATCH_LIMIT} universities per call."
        return json.dumps(data, ensure_ascii=False)

    async def get_unofficial_admissions(
        self,
        institution: Literal["mcmaster", "ualberta", "nus"],
        topic: Literal["requirements", "language", "deadlines", "history"],
    ) -> str:
        """Read vetted third-party pages for schools whose official site cannot be read. Results are UNOFFICIAL and must be labelled "非官方来源，仅供参考" with link and date. Use only after the official tool and the official documents knowledge base.

        :param institution: University ID whose official site is not readable.
        :param topic: Evidence type.
        """
        if institution not in ("mcmaster", "ualberta", "nus") or topic not in ("requirements", "language", "deadlines", "history"):
            return json.dumps({"status": "invalid_public_identifier"}, ensure_ascii=False)
        data = await asyncio.to_thread(collect_unofficial, institution, topic)
        return json.dumps(data, ensure_ascii=False)
