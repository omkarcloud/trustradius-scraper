"""Configuration for the TrustRadius Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT               port the API listens on (default 8000)
    TRUSTRADIUS_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                       (default: none — direct). www.trustradius.com sits behind
                       Cloudflare, which lets most home and office connections
                       through but challenges cloud and datacenter IPs. If every
                       call starts answering 403 "Just a moment...", point
                       TRUSTRADIUS_PROXY at a residential proxy and requests
                       leave through it.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# A page that answers Cloudflare's challenge is retried with a second TLS
# fingerprint on the same connection, then on a fresh connection — this many
# connections in total.
TRUSTRADIUS_EXIT_ATTEMPTS = 3

TRUSTRADIUS_PROXY = os.environ.get("TRUSTRADIUS_PROXY") or None

# The hosted service sends pages and the JSON autocomplete through different
# exits; this kit sends both through the one connection above.
TRUSTRADIUS_EXIT = TRUSTRADIUS_PROXY
TRUSTRADIUS_API_EXIT = TRUSTRADIUS_PROXY


def trustradius_proxy():
    """The proxy for one page session (None = direct)."""
    return os.environ.get("TRUSTRADIUS_PROXY") or None


def trustradius_api_proxy():
    """The proxy for the JSON autocomplete / competitors calls (None = direct)."""
    return os.environ.get("TRUSTRADIUS_PROXY") or None
