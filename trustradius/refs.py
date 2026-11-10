"""Reference resolvers, link builders and the vocabulary tables the
/trustradius/* schemas and parsers share.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair): every resolver takes a bare slug OR any www.trustradius.com
link and returns the slug; it raises ValueError with a user-facing message
(schema_fields.RefField turns it into a 400).

Identifier shapes (www.trustradius.com, researched 2026-11-07):
  product   slug ("hubspot-crm"); links /products/<slug>[/reviews|/pricing|
            /competitors|/features|/details|/reviews/...]. Renamed products
            keep their old slugs as redirects (salesforce-sales-cloud ->
            salesforce-agentforce-sales), which fetch.py follows.
  review    slug "<product>-YYYY-MM-DD-hh-mm-ss[-mmm]" or the 24-hex review
            id (/reviews/<id> redirects to the slug URL); links /reviews/<slug>
  category  slug ("crm"); links /categories/<slug>, or the bare /<slug> path
            the site's own autocomplete hands out for categories
  vendor    slug ("salesforce"); links /vendors/<slug>
  compare   2-3 product refs; the site sorts the slugs alphabetically into
            /compare-products/<a>-vs-<b>[-vs-<c>]

The industry table is the site's own NAICS sector list (chunk
5518-529cb56d61be8a94.js, module 44520, read 2026-11-07): the review filter
`?industry=<slug>` takes the slug, while the facet counts on a reviews page
come back as TrustRadius's internal industry codes (`trCodes`), so the table
maps both ways.
"""
import re
from urllib.parse import unquote, urlparse

SITE = "https://www.trustradius.com"
SITE_HOST = "www.trustradius.com"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,199}$")
HEX_ID_RE = re.compile(r"^[0-9a-f]{24}$")
# "<product>-2025-10-22-09-42-29" or "...-29-332" (a millisecond suffix on newer slugs)
REVIEW_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}(-\d{1,3})?$")


def _is_site_link(value):
    return value.startswith(("http://", "https://", "//"))


def _site_path(value, what):
    """The path segments of a www.trustradius.com link ("//" links get https)."""
    url = value if not value.startswith("//") else "https:" + value
    host = (urlparse(url).hostname or "").lower()
    if not (host == "trustradius.com" or host.endswith(".trustradius.com")):
        raise ValueError(f"Must be a trustradius.com {what} link.")
    return [unquote(seg) for seg in urlparse(url).path.split("/") if seg]


def _slug(value, what, pattern=SLUG_RE):
    slug = value.strip().lower()
    if pattern.match(slug):
        return slug
    raise ValueError(f"Must be a TrustRadius {what} slug or a trustradius.com {what} link.")


def resolve_product(value):
    """Bare product slug or any /products/<slug>... link -> the slug."""
    value = (value or "").strip()
    if _is_site_link(value):
        segs = _site_path(value, "product")
        if len(segs) >= 2 and segs[0] == "products":
            return _slug(segs[1], "product")
        raise ValueError("Must be a trustradius.com product link "
                         "(https://www.trustradius.com/products/<slug>).")
    return _slug(value, "product")


def resolve_review(value):
    """Bare review slug / 24-hex review id or a /reviews/<slug> link -> the slug or id."""
    value = (value or "").strip()
    if _is_site_link(value):
        segs = _site_path(value, "review")
        if len(segs) >= 2 and segs[0] == "reviews":
            value = segs[1]
        else:
            raise ValueError("Must be a trustradius.com review link "
                             "(https://www.trustradius.com/reviews/<slug>).")
    slug = value.strip().lower().split("#")[0]
    if HEX_ID_RE.match(slug) or REVIEW_SLUG_RE.match(slug):
        return slug
    raise ValueError("Must be a TrustRadius review slug (<product>-YYYY-MM-DD-hh-mm-ss), "
                     "a 24-character review id, or a trustradius.com review link.")


def resolve_category(value):
    """Bare category slug, a /categories/<slug> link or the bare /<slug>
    category path -> the slug."""
    value = (value or "").strip()
    if _is_site_link(value):
        segs = _site_path(value, "category")
        if len(segs) >= 2 and segs[0] == "categories":
            return _slug(segs[1], "category")
        if len(segs) == 1 and segs[0] != "categories":
            return _slug(segs[0], "category")
        raise ValueError("Must be a trustradius.com category link "
                         "(https://www.trustradius.com/categories/<slug>).")
    return _slug(value, "category")


def resolve_vendor(value):
    """Bare vendor slug or a /vendors/<slug> link -> the slug."""
    value = (value or "").strip()
    if _is_site_link(value):
        segs = _site_path(value, "vendor")
        if len(segs) >= 2 and segs[0] == "vendors":
            return _slug(segs[1], "vendor")
        raise ValueError("Must be a trustradius.com vendor link "
                         "(https://www.trustradius.com/vendors/<slug>).")
    return _slug(value, "vendor")


def resolve_products(value, min_items=2, max_items=3):
    """A comma list of product refs (slugs or links) -> sorted, deduped slugs
    (the site's own compare URL order). A /compare-products/a-vs-b link is
    accepted whole."""
    value = (value or "").strip()
    if _is_site_link(value):
        segs = _site_path(value, "compare")
        if len(segs) >= 2 and segs[0] == "compare-products":
            value = segs[1].replace("-vs-", ",")
        elif len(segs) >= 2 and segs[0] == "products":
            value = segs[1]
        else:
            raise ValueError("Must be product slugs / links separated by commas, "
                             "or a trustradius.com compare link.")
    slugs = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        slug = resolve_product(item)
        if slug not in slugs:
            slugs.append(slug)
    if len(slugs) < min_items:
        raise ValueError(f"Give at least {min_items} different products to compare.")
    if len(slugs) > max_items:
        raise ValueError(f"At most {max_items} products can be compared.")
    return sorted(slugs)


# ---- links --------------------------------------------------------------------------

def product_link(slug):
    return f"{SITE}/products/{slug}"


def product_reviews_link(slug):
    return f"{SITE}/products/{slug}/reviews"


def review_link(slug):
    return f"{SITE}/reviews/{slug}"


def category_link(slug):
    return f"{SITE}/categories/{slug}"


def vendor_link(slug):
    return f"{SITE}/vendors/{slug}"


def compare_link(slugs):
    return f"{SITE}/compare-products/{'-vs-'.join(sorted(slugs))}"


def absolute(path):
    """A site-relative href ("/reviews/x", "/images/no_photo.png") -> absolute."""
    if not path or not isinstance(path, str):
        return None
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return SITE + (path if path.startswith("/") else "/" + path)


# ---- the reviews filter vocabulary ---------------------------------------------------
# Query params of /products/<slug>/reviews (verified live 2026-11-07, each
# changes the page's totalReviews): sortAttribute=date|rating + sortOrder,
# starRating=5,4 (buckets: 5 = 9-10, 4 = 7-8, 3 = 5-6, 2 = 3-4, 1 = 1-2),
# companySizeGroup=small|medium|large, industry=<slug>, reviewerRoles=...,
# reviewerCountry=<ISO3>, q=<keyword>, lastUpdated=month|3months|6months|year.

SORTS = {
    "recent": ("date", "desc"),
    "oldest": ("date", "asc"),
    "rating_high": ("rating", "desc"),
    "rating_low": ("rating", "asc"),
}
STARS = ("1", "2", "3", "4", "5")
COMPANY_SIZES = {"small": "small", "medium": "medium", "large": "large"}
# public value -> the site's reviewerRoles token
ROLES = {
    "user": "user", "support": "support", "manager": "manager",
    "decision_maker": "decisionMaker", "consultant": "consultant",
    "implementer": "implementer", "reseller": "reseller",
}
UPDATED_WITHIN = {"month": "month", "3months": "3months", "6months": "6months", "year": "year"}

# slug -> (NAICS code, name, TrustRadius industry codes)
INDUSTRIES = {
    "agriculture": ("11", "Agriculture, Forestry, Fishing and Hunting", ("63", "64", "65", "66", "150")),
    "mining": ("21", "Mining, Quarrying, and Oil and Gas Extraction", ("56", "57")),
    "utilities": ("22", "Utilities", ("59", "144")),
    "construction": ("23", "Construction", ("48", "51", "49", "145")),
    "manufacturing": ("31", "Manufacturing", (
        "53", "54", "112", "23", "34", "26", "55", "135", "147", "114", "61", "15", "117", "146", "83",
        "7", "58", "60", "21", "142", "19", "18", "24", "25", "20", "3", "1", "52", "17", "62", "143",
        "111", "12", "138")),
    "wholesale-trade": ("42", "Wholesale Trade", ("133", "134")),
    "retail-trade": ("44", "Retail Trade", ("27", "22")),
    "transportation": ("48", "Transportation and Warehousing", ("92", "94", "95", "87", "116", "93")),
    "information": ("51", "Information", (
        "4", "5", "6", "8", "36", "35", "82", "81", "84", "109", "113", "115", "119", "126", "127", "103")),
    "finance-and-insurance": ("52", "Finance and Insurance", ("41", "42", "43", "45", "46", "129", "106")),
    "real-estate": ("53", "Real Estate and Rental and Leasing", ("44", "128")),
    "professional-services": ("54", "Professional, Scientific, and Technical Services", (
        "9", "10", "47", "50", "96", "11", "80", "97", "98", "99", "70", "118", "136", "140", "108", "16",
        "120", "137")),
    "management": ("55", "Management of Companies and Enterprises", ("76",)),
    "admin-and-support": ("56", "Administrative and Support Services", ("104", "121", "122", "86", "123", "110")),
    "education": ("61", "Educational Services", ("67", "68", "69", "132", "105", "85")),
    "health-care": ("62", "Health Care and Social Assistance", ("14", "13", "139", "124", "88", "125")),
    "arts-and-entertainment": ("71", "Arts, Entertainment, and Recreation", ("28", "33", "29", "37", "38", "39", "40")),
    "accommodation-and-food": ("72", "Accommodation and Food Services", ("31", "32", "30")),
    "other-services": ("81", "Other Services (except Public Administration)", ("91", "89", "90", "100", "131", "101")),
    "public-administration": ("92", "Public Administration", (
        "75", "71", "72", "73", "74", "77", "78", "79", "148", "107", "130", "141", "102")),
}
INDUSTRY_BY_TR_CODE = {code: slug for slug, (_, _, codes) in INDUSTRIES.items() for code in codes}
INDUSTRY_BY_NAICS = {naics: slug for slug, (naics, _, _) in INDUSTRIES.items()}


def industry_for_tr_code(code):
    """A TrustRadius industry code (reviews facet) -> {slug, name} or None."""
    slug = INDUSTRY_BY_TR_CODE.get(str(code))
    if not slug:
        return None
    return {"slug": slug, "name": INDUSTRIES[slug][1]}


# ---- category listing filters ----------------------------------------------------------
# /categories/<slug>?f=<offset>&hp=true&free-pricing=true&top=true&os=windows|mac|linux
# (chunk page-1c259f8fcb892c0a.js; `company-size` only reorders, so it is not
# exposed). 25 per page; the listing stops at offset 975 (40 pages).
CATEGORY_PAGE_SIZE = 25
CATEGORY_MAX_PAGE = 40
OPERATING_SYSTEMS = ("windows", "mac", "linux")

SEARCH_TYPES = {"product": "product", "vendor": "vendor", "category": "category"}
ALTERNATIVE_SEGMENTS = ("all", "small", "medium", "large")
