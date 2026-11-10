"""The /trustradius/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching (cache.cached_call, keyed on the validated params):

  * products/details merges TWO cached page parses — the product page
    (trustradius.product) and the pricing page (trustradius.pricing) — plus a
    cached vendor-name -> slug lookup (trustradius.vendor_lookup, the product
    page carries no vendor slug), so a client reading details twice pays
    three fetches once.
  * products/reviews caches each filtered page (trustradius.reviews); the
    AI-insights card on page 1 is what products/insights reuses, so a client
    reading reviews page 1 and insights pays the page once.
  * products/alternatives caches the whole competitors page
    (trustradius.alternatives) and slices it per segment.
  * every other endpoint caches its own response.

Pagination: reviews are 10 per page with the site's own total, categories
25 per page up to the site's offset cap (40 pages); a page past the end is
an empty page.
"""
import math

from cache import cached_call
from trustradius import cache_config as ttl
from trustradius import parsers, refs
from trustradius.fetch import (TrustradiusNotFound, fetch_categories_index, fetch_category, fetch_compare,
                               fetch_competitors, fetch_complete, fetch_product, fetch_product_pricing,
                               fetch_review, fetch_review_insights, fetch_reviews, fetch_vendor)

REVIEWS_PAGE_SIZE = 10


# ---- products/search -----------------------------------------------------------------

def _search(query, type, limit):
    results = parsers.parse_search(fetch_complete(query, type, max(limit, 1)), type)
    results = [r for r in results if r["type"] == type][:limit]
    return {"query": query, "type": type, "count": len(results), "results": results}


def products_search(**data):
    return cached_call("trustradius.search", data, _search, ttl.SEARCH_CACHE)


# ---- the shared product records --------------------------------------------------------

def _product_record(product):
    record = parsers.parse_product(fetch_product(product), product)
    if record is None:
        raise TrustradiusNotFound(f"product {product} not found")
    return record


def _pricing_record(product):
    record = parsers.parse_pricing(fetch_product_pricing(product), product)
    if record is None:
        raise TrustradiusNotFound(f"product {product} not found")
    return record


def _product(product):
    return cached_call("trustradius.product", {"product": product}, _product_record, ttl.PRODUCT_CACHE)


def _pricing(product):
    return cached_call("trustradius.pricing", {"product": product}, _pricing_record, ttl.PRICING_CACHE)


def _vendor_lookup(name):
    """vendor name -> slug through the site's own autocomplete (exact,
    case-insensitive name match), or None."""
    hits = parsers.parse_search(fetch_complete(name, "vendor", 20), "vendor")
    for hit in hits:
        if (hit.get("name") or "").strip().lower() == name.strip().lower():
            return hit["slug"]
    return hits[0]["slug"] if len(hits) == 1 else None


def _vendor_slug(name):
    if not name:
        return None
    try:
        return cached_call("trustradius.vendor_lookup", {"name": name}, _vendor_lookup, ttl.VENDOR_LOOKUP_CACHE)
    except Exception:
        return None     # the lookup is a convenience; details must not fail on it


# ---- products/details ----------------------------------------------------------------

def product_details(product):
    """The product page + the pricing page, merged: identity, vendor,
    categories, ratings (with trScore and the written / quick split), awards,
    feature scores, pros / cons, FAQs, media, integrations, competitors, the
    HG Insights install share, 5 featured full reviews, and the pricing slice
    (starting price, editions, free / trial flags, support, quotes,
    alternatives)."""
    record = dict(_product(product))
    pricing = dict(_pricing(record["slug"]))
    vendor = dict(record.get("vendor") or {})
    if vendor and not vendor.get("slug"):
        slug = _vendor_slug(vendor.get("name"))
        vendor["slug"] = slug
        vendor["link"] = refs.vendor_link(slug) if slug else None
    record["vendor"] = vendor or None
    record["logo"] = record.get("logo") or vendor.get("logo")
    rating = pricing.pop("rating", None) or record.get("rating")
    record["rating"] = rating
    pricing.pop("slug", None)
    if not record.get("operating_systems"):
        record["operating_systems"] = pricing.get("operating_systems") or []
    pricing.pop("operating_systems", None)
    if not record.get("pricing_link"):
        record["pricing_link"] = pricing.get("pricing_link")
    pricing.pop("pricing_link", None)
    featured = record.pop("featured_reviews", [])
    record["pricing"] = pricing
    record["featured_reviews"] = featured
    return record


# ---- products/reviews ----------------------------------------------------------------

def _reviews_params(page, sort, stars, company_size, industry, role, country, keyword, updated_within):
    params = {}
    if page and page > 1:
        params["page"] = page
    attribute, order = refs.SORTS.get(sort or "recent", refs.SORTS["recent"])
    if (sort or "recent") != "recent":
        params["sortAttribute"] = attribute
        params["sortOrder"] = order
    if stars:
        params["starRating"] = ",".join(sorted(stars, reverse=True))
    if company_size:
        params["companySizeGroup"] = company_size
    if industry:
        params["industry"] = industry
    if role:
        params["reviewerRoles"] = role
    if country:
        params["reviewerCountry"] = country
    if keyword:
        params["q"] = keyword
    if updated_within:
        params["lastUpdated"] = updated_within
    return params


def _reviews_page(product, page=1, sort="recent", stars=None, company_size=None, industry=None, role=None,
                  country=None, keyword=None, updated_within=None):
    page_html = fetch_reviews(product, _reviews_params(page, sort, stars, company_size, industry, role, country,
                                                       keyword, updated_within))
    parsed = parsers.parse_reviews_page(page_html)
    if parsed.get("product") is None and not parsed["reviews"]:
        raise TrustradiusNotFound(f"product {product} not found")
    total = parsed.get("total_reviews")
    total_pages = parsed.get("total_pages")
    if total_pages is None and total is not None:
        total_pages = math.ceil(total / REVIEWS_PAGE_SIZE)
    return {
        "product": parsed.get("product"),
        "filters": {"sort": sort or "recent", "stars": stars, "company_size": company_size, "industry": industry,
                    "role": role, "country": country, "keyword": keyword, "updated_within": updated_within},
        "facets": parsed.get("facets"),
        "insights_summary": parsers.parse_insights_glimpse(page_html) if page == 1 else None,
        "results": parsed["reviews"],
        "pagination": {
            "page": page,
            "items_per_page": REVIEWS_PAGE_SIZE,
            "total_pages": total_pages or 0,
            "total_count": total,
        },
    }


def _reviews_key(product, page=1, sort="recent", **filters):
    data = {"product": product, "page": page, "sort": sort or "recent"}
    for name in ("stars", "company_size", "industry", "role", "country", "keyword", "updated_within"):
        data[name] = filters.get(name)
    return data


def products_reviews(**data):
    key = _reviews_key(**data)
    return cached_call("trustradius.reviews", key, _reviews_page, ttl.REVIEWS_CACHE)


# ---- reviews/details -----------------------------------------------------------------

def _review_details(review):
    record = parsers.parse_review(fetch_review(review))
    if record is None:
        raise TrustradiusNotFound(f"review {review} not found")
    return record


def reviews_details(**data):
    return cached_call("trustradius.review", data, _review_details, ttl.REVIEW_CACHE)


# ---- products/alternatives -----------------------------------------------------------

def _alternatives_record(product):
    record = parsers.parse_competitors(fetch_competitors(product))
    if record is None:
        raise TrustradiusNotFound(f"product {product} not found")
    return record


def products_alternatives(product, segment="all"):
    """The site's competitors list plus its "best alternatives" ranking for
    one reviewer company-size segment (all / small / medium / large), both
    with ratings and per-feature scores."""
    record = cached_call("trustradius.alternatives", {"product": product}, _alternatives_record,
                         ttl.ALTERNATIVES_CACHE)
    segment = segment or "all"
    alternatives = record["alternatives"].get(segment, [])
    return {
        "product": {"slug": product, "link": refs.product_link(product)},
        "segment": segment,
        "competitors_count": len(record["competitors"]),
        "competitors": record["competitors"],
        "alternatives_count": len(alternatives),
        "alternatives": alternatives,
    }


# ---- products/insights -----------------------------------------------------------------

def _insights(product):
    synthesis = parsers.parse_insights(fetch_review_insights(product))
    if synthesis is None:
        raise TrustradiusNotFound(f"TrustRadius has not published review insights for {product}")
    summary = None
    try:
        summary = products_reviews(**_reviews_key(product)).get("insights_summary")
    except Exception:
        summary = None        # the overview card is a bonus; the synthesis is the record
    return {
        "product": {"slug": product, "link": refs.product_link(product),
                    "insights_link": refs.product_reviews_link(product) + "/review-insights"},
        "title": synthesis.get("title"),
        "based_on_reviews": synthesis.get("based_on_reviews") or (summary or {}).get("based_on_reviews"),
        "last_published": (summary or {}).get("last_published"),
        "overview": (summary or {}).get("overview") or [],
        "pros": (summary or {}).get("pros") or [],
        "cons": (summary or {}).get("cons") or [],
        "hg_insights_installs": (summary or {}).get("hg_insights_installs"),
        "dimensions": synthesis.get("dimensions") or [],
        "industry_segments": synthesis.get("industry_segments") or [],
        "questions": synthesis.get("questions") or [],
    }


def products_insights(**data):
    return cached_call("trustradius.insights", data, _insights, ttl.INSIGHTS_CACHE)


# ---- products/compare ------------------------------------------------------------------

def _compare(products):
    record = parsers.parse_compare(fetch_compare(products))
    if record is None:
        raise TrustradiusNotFound(f"comparison {' vs '.join(products)} not found")
    return record


def products_compare(**data):
    return cached_call("trustradius.compare", data, _compare, ttl.COMPARE_CACHE)


# ---- categories/products ---------------------------------------------------------------

def _category_params(page, free, top_rated, os):
    params = {}
    if page and page > 1:
        params["f"] = (page - 1) * refs.CATEGORY_PAGE_SIZE
    if free:
        params["free-pricing"] = "true"
    if top_rated:
        params["top"] = "true"
    if os:
        params["os"] = os
    return params


def _category_page(category, page=1, free=None, top_rated=None, os=None):
    parsed = parsers.parse_category(fetch_category(category, _category_params(page, free, top_rated, os)))
    if parsed is None:
        raise TrustradiusNotFound(f"category {category} not found")
    total = parsed.get("total")
    total_pages = min(math.ceil(total / refs.CATEGORY_PAGE_SIZE), refs.CATEGORY_MAX_PAGE) if total else 0
    return {
        "category": parsed["category"],
        "filters": {"free": bool(free) if free is not None else None,
                    "top_rated": bool(top_rated) if top_rated is not None else None, "os": os},
        "results": parsed["products"],
        "pagination": {
            "page": page,
            "items_per_page": refs.CATEGORY_PAGE_SIZE,
            "total_pages": total_pages,
            "total_count": total,
        },
    }


def categories_products(**data):
    return cached_call("trustradius.category", data, _category_page, ttl.CATEGORY_CACHE)


# ---- categories/list -------------------------------------------------------------------

def _categories_list():
    groups = parsers.parse_categories_index(fetch_categories_index())
    if groups is None:
        raise TrustradiusNotFound("categories index not found")
    return {"groups_count": len(groups), "categories_count": sum(g["categories_count"] for g in groups),
            "groups": groups}


def categories_list(**data):
    return cached_call("trustradius.categories", {}, _categories_list, ttl.CATEGORIES_LIST_CACHE)


# ---- vendors/details -------------------------------------------------------------------

def _vendor_details(vendor):
    record = parsers.parse_vendor(fetch_vendor(vendor))
    if record is None:
        raise TrustradiusNotFound(f"vendor {vendor} not found")
    return record


def vendors_details(**data):
    return cached_call("trustradius.vendor", data, _vendor_details, ttl.VENDOR_CACHE)
