"""TrustRadius transport: plain curl_cffi with browser-impersonated TLS. No
browser, no login, no cookies to mint — everything this package reads is
what a logged-out visitor gets.

Upstream surfaces (researched 2026-11-07):

  * PAGES    www.trustradius.com's Next.js app-router pages, whose data
             rides in the React Flight payload (`self.__next_f.push` rows,
             parsers.flight_tree): /products/<slug>, /products/<slug>/pricing,
             /products/<slug>/reviews (+ filter params), /products/<slug>/
             reviews/review-insights, /categories/<slug>?f=<offset>,
             /categories, /compare-products/<a>-vs-<b>[-vs-<c>]. Three pages
             are still the old server: /reviews/<slug> (window.__INITIAL_DATA__
             .review), /products/<slug>/competitors (window.__INITIAL_DATA__)
             and /vendors/<slug> (window.__SERVER_REDUX_STATE__.vendorPage).
             Unknown slugs answer a real HTTP 404; a renamed product 308s to
             its new slug (followed); a product without an AI synthesis 307s
             from /review-insights back to /reviews?synthesisUnavailable=…
             (mapped to NotFound).

  * JSON     /api/v1/complete?q=&t=product|vendor|category&ms=100 (the
             site's own autocomplete: id, name, slug, path) and
             /api/v1/product-competitors?productSlugs=&limit=15. Open to every
             exit, including the ones whose HTML requests are challenged.

Cloudflare: a managed challenge ("Just a moment...", HTTP 403, header
cf-mitigated: challenge) scored per exit IP AND per TLS fingerprint. Pod probe
2026-11-07 (config.py's trustradius block): the pod's own IP and every
datacenter port are challenged on all HTML pages; US residential exits pass
about two in three, and on a challenged exit the safari17_0 profile sometimes
passes where chrome does not (and the reverse). So: HTML rides a sticky US
residential exit per thread (config.TRUSTRADIUS_EXIT), a challenge first
retries the SAME exit with the next TLS profile (PROFILES), then drops the
exit; the JSON calls ride the direct tier (config.TRUSTRADIUS_API_EXIT).

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  TrustradiusUpstreamError  transport failure / 5xx / malformed payload  — retryable
  TrustradiusBlocked        403 / 429 / the Cloudflare challenge page     — retryable on a fresh exit
  TrustradiusBadRequest     upstream 400                                 — never retried
  TrustradiusNotFound       unknown slug (HTTP 404), no synthesis (307)  — never retried
"""
import os
import re
import sys
import threading
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from trustradius.refs import SITE

# TLS profiles tried on ONE exit before it is dropped: Cloudflare's verdict
# differs per (exit, fingerprint) — on 2026-11-07 20 proxy exits gave
# chrome 0/20 while safari17_0 passed 4/20, hours earlier chrome was the one
# that passed on the same site (research note trustradius-scraper-research).
PROFILES = ("chrome", "safari17_0")
PAGE_TIMEOUT = 45        # compare pages run to 1.2 MB, review pages to 1.1 MB
API_TIMEOUT = 20
BLOCK_RETRY_PAUSE = 0.3  # a block is cured by a fresh profile / exit, not by waiting

PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "referer": SITE + "/",
}

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_CHALLENGE_MARKERS = ("just a moment", "cf-chl", "challenge-platform", "attention required",
                      "_cf_chl_opt")


class TrustradiusUpstreamError(UpstreamError):
    """Transport failure, 5xx or a malformed payload — retryable."""


class TrustradiusBlocked(TrustradiusUpstreamError, Blocked):
    """403 / 429 or the Cloudflare challenge page — retryable on a fresh profile / exit."""


class TrustradiusBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class TrustradiusNotFound(NotFound):
    """The product / review / category / vendor / comparison does not exist."""


# ---- sessions ----------------------------------------------------------------
# One session per cheroot worker thread per surface class (pages vs JSON):
# a curl handle must not be shared across threads. A page session keeps its
# sticky exit and its TLS profile index for its lifetime; a challenge moves
# it to the next profile on the same exit, and when the profiles are
# exhausted the session (and so the exit) is dropped.
_local = threading.local()


def _new_session(proxy, profile):
    from curl_cffi import requests as curl_requests
    sess = curl_requests.Session(impersonate=profile)
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    sess.headers["accept-language"] = egress.accept_language(proxy)
    sess.tr_proxy = proxy
    sess.tr_profile = profile
    return sess


def _page_session():
    sess = getattr(_local, "page", None)
    if sess is None:
        sess = _new_session(config.trustradius_proxy(), PROFILES[0])
        _local.page = sess
    return sess


def _api_session():
    sess = getattr(_local, "api", None)
    if sess is None:
        sess = _new_session(config.trustradius_api_proxy(), PROFILES[0])
        _local.api = sess
    return sess


def _close(sess):
    try:
        sess.close()
    except Exception:
        pass


def _rotate_page_session():
    """After a challenge: the same exit with the next TLS profile, or a fresh
    exit (profile 0) when every profile was refused. Returns True when the
    exit was kept."""
    sess = getattr(_local, "page", None)
    _local.page = None
    if sess is None:
        return False
    _close(sess)
    idx = PROFILES.index(sess.tr_profile) if sess.tr_profile in PROFILES else len(PROFILES)
    if idx + 1 < len(PROFILES):
        _local.page = _new_session(sess.tr_proxy, PROFILES[idx + 1])
        return True
    return False


def _drop(which):
    sess = getattr(_local, which, None)
    setattr(_local, which, None)
    if sess is not None:
        _close(sess)


def _retrying(fn, which="page"):
    """Run fn() under the retry policy: a block gets
    config.TRUSTRADIUS_EXIT_ATTEMPTS fresh exits (each with every TLS
    profile) and no backoff; any other upstream failure config.MAX_RETRIES
    with backoff; NotFound / BadRequest surface immediately."""
    last = None
    exits_tried, plain_failures = 0, 0
    max_blocked = config.TRUSTRADIUS_EXIT_ATTEMPTS * len(PROFILES)
    for _ in range(max_blocked + config.MAX_RETRIES):
        try:
            return fn()
        except TrustradiusBlocked as e:
            last = e
            if which == "page":
                kept_exit = _rotate_page_session()
            else:
                _drop(which)
                kept_exit = False
            if not kept_exit:
                exits_tried += 1
                if exits_tried >= config.TRUSTRADIUS_EXIT_ATTEMPTS:
                    break
            time.sleep(BLOCK_RETRY_PAUSE)
        except TrustradiusUpstreamError as e:
            last = e
            plain_failures += 1
            _drop(which)
            if plain_failures >= config.MAX_RETRIES:
                break
            time.sleep(config.RETRY_BACKOFF * plain_failures)
    raise last


# ---- classification ----------------------------------------------------------

def page_title(text):
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def is_challenge(text):
    head = (text or "")[:6000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


def _classify(resp, label):
    """Map an HTTP response to the taxonomy; return the body text."""
    status = resp.status_code
    if status == 404:
        raise TrustradiusNotFound(f"{label} not found")
    if status == 400:
        raise TrustradiusBadRequest(resp.text[:200])
    if status in (401, 403, 429, 503) or resp.headers.get("cf-mitigated"):
        raise TrustradiusBlocked(f"HTTP {status} for {label}"
                                 + (" (Cloudflare challenge)" if is_challenge(resp.text) else ""))
    if status != 200:
        raise TrustradiusUpstreamError(f"HTTP {status} for {label}")
    text = resp.text
    # the challenge page names its zone ("cZone: 'www.trustradius.com'") in
    # its head, so only the <title> tells it from a real page ("… | TrustRadius")
    if is_challenge(text) and "trustradius" not in page_title(text).lower():
        raise TrustradiusBlocked(f"Cloudflare challenge page for {label}")
    return text


def _get_page(path, label, params=None, not_found_redirect=None):
    """GET a site page (redirects followed: renamed slugs 308 to the new
    one). `not_found_redirect` is a query marker whose presence in the final
    URL means the site bounced us to a fallback page (no synthesis)."""
    url = SITE + path + (("?" + urlencode(params, doseq=True)) if params else "")

    def once():
        try:
            resp = _page_session().get(url, headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT,
                                       allow_redirects=True)
        except Exception as e:
            raise TrustradiusUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if not_found_redirect and not_found_redirect in str(resp.url):
            raise TrustradiusNotFound(f"{label} not found")
        text = _classify(resp, label)
        if not text or len(text) < 2000:
            raise TrustradiusUpstreamError(f"short page for {label} ({len(text or '')} bytes)")
        return text
    return _retrying(once, "page")


def _get_json(path, label, params):
    url = SITE + path + "?" + urlencode(params, doseq=True)

    def once():
        try:
            resp = _api_session().get(url, headers=API_HEADERS, timeout=API_TIMEOUT)
        except Exception as e:
            raise TrustradiusUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, label)
        try:
            return resp.json()
        except Exception:
            raise TrustradiusBlocked(f"non-JSON {label} response: {text[:120]}")
    return _retrying(once, "api")


# ---- pages -------------------------------------------------------------------

def fetch_product(slug):
    """GET /products/<slug> — the product page (ratings, awards, features, FAQs)."""
    return _get_page(f"/products/{slug}", f"product {slug}")


def fetch_product_pricing(slug):
    """GET /products/<slug>/pricing — editions, quotes, free / trial flags."""
    return _get_page(f"/products/{slug}/pricing", f"product {slug}")


def fetch_reviews(slug, params=None):
    """GET /products/<slug>/reviews with the site's filter / sort / page params."""
    return _get_page(f"/products/{slug}/reviews", f"product {slug}", params or {})


def fetch_review_insights(slug):
    """GET /products/<slug>/reviews/review-insights — the AI synthesis page.
    A product without one is bounced to /reviews?synthesisUnavailable=product."""
    return _get_page(f"/products/{slug}/reviews/review-insights", f"review insights for {slug}",
                     not_found_redirect="synthesisUnavailable")


def fetch_competitors(slug):
    """GET /products/<slug>/competitors — the old server's alternatives page."""
    return _get_page(f"/products/{slug}/competitors", f"product {slug}")


def fetch_review(slug):
    """GET /reviews/<slug or id> — one review's full questionnaire."""
    return _get_page(f"/reviews/{slug}", f"review {slug}")


def fetch_vendor(slug):
    """GET /vendors/<slug> — the vendor profile + every product."""
    return _get_page(f"/vendors/{slug}", f"vendor {slug}")


def fetch_category(slug, params=None):
    """GET /categories/<slug>?f=<offset>&... — one listing page (25 products)."""
    return _get_page(f"/categories/{slug}", f"category {slug}", params or {})


def fetch_categories_index():
    """GET /categories — the whole category tree."""
    return _get_page("/categories", "categories")


def fetch_compare(slugs):
    """GET /compare-products/<a>-vs-<b>[-vs-<c>] (slugs sorted, like the site)."""
    key = "-vs-".join(sorted(slugs))
    return _get_page(f"/compare-products/{key}", f"comparison {key}")


# ---- JSON --------------------------------------------------------------------

def fetch_complete(query, kind="product", max_results=100):
    """GET /api/v1/complete — [{slug: <group>, name, options: [{_id, path, text, slug}]}]."""
    payload = _get_json("/api/v1/complete", "search", {"q": query, "t": kind, "ms": max_results})
    if not isinstance(payload, list):
        raise TrustradiusUpstreamError(f"unexpected search payload shape: {str(payload)[:120]}")
    return payload


def fetch_product_competitors(slug, limit=15):
    """GET /api/v1/product-competitors — up to 15 competitor stubs (id, name, slug, vendor, logo)."""
    payload = _get_json("/api/v1/product-competitors", f"competitors of {slug}",
                        {"productSlugs": slug, "limit": limit})
    if not isinstance(payload, list):
        raise TrustradiusUpstreamError(f"unexpected competitors payload shape: {str(payload)[:120]}")
    return payload
