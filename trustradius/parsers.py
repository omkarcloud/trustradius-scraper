"""Raw TrustRadius pages / JSON -> clean dicts. Pure functions, no I/O.

Fixtures (trustradius/fixtures/, captured 2026-11-07 from www.trustradius.com;
`competitors_salesforce.html` has its 6 MB `window.__SERVER_REDUX_STATE__`
object, which nothing here reads, replaced by `{}`). Scrubbed 2026-11-10 for
the public repo, every edit keeping the byte length so Flight text rows stay
valid: reviewer and vendor-staff e-mails, contact names and phones x-ed out,
`apiKeyEncrypted` zeroed, and the login-secret word in category / SSO feature
text spelled "passcode" (it trips the open-source secret scan):

  product_salesforce.html / product_korero.html          /products/<slug> (rich / sparse)
  product_pricing_salesforce.html / product_pricing_korero.html
  reviews_salesforce_p1.html, reviews_hubspot_p2.html,   /products/<slug>/reviews
  reviews_hubspot_industry.html (?industry=...),
  reviews_korero.html (3 reviews), reviews_hubspot_past_end.html (?page=178: 0 cards)
  review_salesforce_full.html / review_salesforce_sparse.html   /reviews/<slug>
  insights_salesforce.html                                /products/<slug>/reviews/review-insights
  competitors_salesforce.html / competitors_korero.html   /products/<slug>/competitors
  vendor_salesforce.html / vendor_hubspot.html            /vendors/<slug>
  category_crm_p1.html / category_crm_f25.html            /categories/crm[?f=25]
  categories_index.html                                   /categories
  compare_hubspot_vs_salesforce.html / compare_three_products.html
  complete_*.json, competitors_api_hubspot.json           /api/v1/complete, /api/v1/product-competitors
  *_notfound.html (HTTP 404 bodies), cloudflare_challenge.html

Three page families:

  * FLIGHT  the Next.js app-router pages stream their React tree as Flight
            rows inside `self.__next_f.push([1,"<row>\n"])` scripts. A row is
            `<hex id>:<json>`; `$<id>` / `$L<id>` strings inside the JSON are
            references to other rows, `T<hex byte length>,<text>` rows are
            plain text (lengths are UTF-8 BYTES), `I[...]` rows are client
            component imports. flight_tree() decodes and resolves them; the
            data then sits either in plain dicts (the product object, a
            category's initialData) or in the props of rendered elements
            (["$", tag, key, props]), which the element helpers walk.
  * STATE   the old server's pages embed `window.__INITIAL_DATA__ = {...}`
            (review page, competitors page) or `window.__SERVER_REDUX_STATE__`
            (vendor page) as JSON object literals.
  * JSON    the two /api/v1 calls.
"""
import html as htmllib
import json
import math
import re
from datetime import datetime

from trustradius import refs
from trustradius.refs import absolute

# ---- generic helpers ----------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>|</p>|</li>|</div>|</h\d>", re.I)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_PRICE_RE = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)")
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY", "A$": "AUD", "C$": "CAD"}


def clean_str(value):
    """A trimmed string, or None for empty / non-string values."""
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value or None


def html_text(markup):
    """Visible text of an HTML fragment: block ends become newlines, tags
    are dropped, entities unescaped, whitespace tidied. None when empty."""
    if not isinstance(markup, str) or not markup.strip():
        return None
    text = _BR_RE.sub("\n", markup)
    text = _TAG_RE.sub("", text)
    text = htmllib.unescape(text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    out = "\n".join(line for line in lines if line)
    return out or None


def iso_date(value):
    """'2025-11-05T19:21:30.915Z' / '2025-11-05' -> '2025-11-05'; None otherwise."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    head = value[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
    except ValueError:
        return None
    return head


def iso_datetime(value):
    """An upstream ISO timestamp -> 'YYYY-MM-DDTHH:MM:SSZ' (UTC); None otherwise."""
    if not isinstance(value, str) or "T" not in value:
        return iso_date(value)
    try:
        parsed = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def number(value):
    """int / float / numeric string -> number; None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = _PRICE_RE.search(value.replace(",", ""))
        if match:
            text = match.group(1).replace(",", "")
            try:
                return int(text) if re.fullmatch(r"-?\d+", text) else float(text)
            except ValueError:
                return None
    return None


def price(value, default_currency="USD"):
    """'$25.00' / '$$54' / '49' / 25 -> {amount, currency}; None when there is no
    amount. The site shows a stray doubled '$' on some editions."""
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"amount": value, "currency": default_currency}
    if not isinstance(value, str):
        return None
    text = value.strip()
    currency = default_currency
    for symbol, code in sorted(_CURRENCY_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if symbol in text:
            currency = code
            break
    amount = number(text)
    if amount is None:
        return None
    return {"amount": amount, "currency": currency}


def _logo(logos, *extra):
    """The best image out of a TrustRadius logos dict ({default, square180,
    squareOriginal, square50}) or plain URL strings."""
    if isinstance(logos, dict):
        for key in ("squareOriginal", "square180", "default", "square50"):
            if clean_str(logos.get(key)):
                return logos[key]
    for value in extra:
        if clean_str(value):
            return value
    return None


def _rating(rating):
    """The site's rating object -> {average, count, tr_score, written_reviews,
    quick_ratings}. `avg` is the 0-10 mean shown on the page, `trScore` the
    recency-weighted score, reviewsRating = written reviews, simpleRating =
    one-click ratings."""
    if not isinstance(rating, dict):
        return None
    out = {
        "average": number(rating.get("avg")),
        "count": number(rating.get("count")),
        "tr_score": number(rating.get("trScore")),
    }
    for key, name in (("reviewsRating", "written_reviews"), ("simpleRating", "quick_ratings")):
        sub = rating.get(key)
        out[name] = ({"average": number(sub.get("avg")), "count": number(sub.get("count")),
                      "tr_score": number(sub.get("trScore"))}
                     if isinstance(sub, dict) else None)
    return out


def _feature_scores(items):
    """[{name, trScore|score, count|ratingsCount, categoryAverage?, slug?}] -> clean list."""
    out = []
    for item in items or []:
        if not isinstance(item, dict) or not clean_str(item.get("name")):
            continue
        row = {
            "name": item["name"],
            "score": number(item.get("score", item.get("trScore"))),
            "ratings_count": number(item.get("count", item.get("ratingsCount"))),
        }
        if "categoryAverage" in item:
            row["category_average"] = number(item.get("categoryAverage"))
        if clean_str(item.get("slug")):
            row["slug"] = item["slug"]
        feature = item.get("feature")
        if isinstance(feature, dict) and clean_str(feature.get("shortDescription")):
            row["description"] = feature["shortDescription"]
        out.append(row)
    return out


def _award(award):
    if not isinstance(award, dict):
        return None
    return {
        "title": clean_str(award.get("title")),
        "type": clean_str(award.get("awardType")),
        "state": clean_str(award.get("awardState")),
        "published_date": iso_date(award.get("publishedDate")),
        "expiration_date": iso_date(award.get("expirationDate")),
        "badge": clean_str(award.get("awardBadgeFileName")),
    }


def _source(source):
    """{trusted, incentive, source} -> {is_trusted, incentive, channel}."""
    if not isinstance(source, dict):
        return None
    return {
        "is_trusted": bool(source.get("trusted")) if source.get("trusted") is not None else None,
        "incentive": clean_str(source.get("incentive")),
        "channel": clean_str(source.get("source")),
    }


def _reviewer(info):
    """The reviewer block the new pages attach to a review card / quote."""
    if not isinstance(info, dict):
        return None
    verification = info.get("verification") or {}
    name = clean_str(info.get("fullName")) or " ".join(
        part for part in (clean_str(info.get("firstName")), clean_str(info.get("lastName"))) if part) or None
    return {
        "id": clean_str(info.get("userId")),
        "name": name,
        "title": clean_str(info.get("title")),
        "job_type": clean_str(info.get("jobType")),
        "department": clean_str(info.get("department")),
        "company": clean_str(info.get("companyName")),
        "company_size": clean_str(info.get("companySize")),
        "industry": clean_str(info.get("industryType")),
        "years_of_experience": number(info.get("yearsExperience")),
        "avatar": absolute(clean_str(info.get("reviewAuthorImageUrl"))),
        "linkedin_link": clean_str(info.get("linkedInProfileUrl")),
        "is_linkedin_verified": bool(verification.get("isVerified")) if isinstance(verification, dict) and verification else None,
        "is_public": bool(info.get("authorPublic")) if info.get("authorPublic") is not None else None,
    }


# ---- Flight (React Server Components) decoding ---------------------------------

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_ROW_HEAD_RE = re.compile(r"([0-9a-fA-F]+):")
_TEXT_HEAD_RE = re.compile(r"T([0-9a-fA-F]+),")
_REF_RE = re.compile(r"^\$[LW@S]?[0-9a-fA-F]+$")


def rsc_payload(page):
    """Concatenate the page's `self.__next_f.push` chunks into one Flight payload."""
    return "".join(json.loads('"' + chunk + '"') for chunk in _PUSH_RE.findall(page or ""))


def flight_rows(payload):
    """Flight payload -> {row id: value}. Text rows become str, JSON rows the
    parsed value, module imports ("I") / hints the tuple (prefix, raw)."""
    rows = {}
    i, n = 0, len(payload)
    while i < n:
        head = _ROW_HEAD_RE.match(payload, i)
        if not head:
            j = payload.find("\n", i)
            if j < 0:
                break
            i = j + 1
            continue
        rid = head.group(1)
        i = head.end()
        text_head = _TEXT_HEAD_RE.match(payload, i)
        if text_head:
            length = int(text_head.group(1), 16)          # UTF-8 bytes, not characters
            start = i + text_head.end() - i
            start = text_head.end()
            text = payload[start:start + length].encode("utf-8")[:length].decode("utf-8", "ignore")
            rows[rid] = text
            i = start + len(text)
            if payload.startswith("\n", i):
                i += 1
            continue
        j = payload.find("\n", i)
        if j < 0:
            j = n
        body = payload[i:j]
        if body[:1] in ("I", "E", "H", "W") and not body.startswith(("[", "{", '"')):
            rows[rid] = (body[0], body[1:])
        else:
            try:
                rows[rid] = json.loads(body)
            except ValueError:
                rows[rid] = ("raw", body)
        i = j + 1
    return rows


def resolve(obj, rows, _depth=0):
    """Replace `$<id>` / `$L<id>` references with the referenced rows
    (recursively) and `$$x` escapes with `$x`. Module-import rows stay as
    tuples (a client component's type)."""
    if _depth > 60:
        return obj
    if isinstance(obj, str):
        if obj == "$undefined":
            return None
        if obj.startswith("$$"):
            return obj[1:]
        if _REF_RE.match(obj):
            ref = obj[1:]
            if ref[:1] in "LW@S":
                ref = ref[1:]
            if ref in rows:
                return resolve(rows[ref], rows, _depth + 1)
        return obj
    if isinstance(obj, list):
        return [resolve(item, rows, _depth + 1) for item in obj]
    if isinstance(obj, dict):
        return {key: resolve(value, rows, _depth + 1) for key, value in obj.items()}
    return obj


def flight_tree(page):
    """The page's resolved Flight rows as one list (every row resolved)."""
    rows = flight_rows(rsc_payload(page))
    return [resolve(value, rows) for key, value in rows.items() if not isinstance(value, tuple)]


def is_element(obj):
    """["$", type, key, props] — a rendered React element."""
    return isinstance(obj, list) and len(obj) == 4 and obj[0] == "$" and isinstance(obj[3], dict)


def iter_elements(obj, _depth=0):
    """Every element in a resolved tree, depth-first (shared subtrees repeat)."""
    if _depth > 200:
        return
    if is_element(obj):
        yield obj
        for value in obj[3].values():
            yield from iter_elements(value, _depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_elements(item, _depth + 1)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from iter_elements(value, _depth + 1)


def find_elements(obj, pred):
    return [el for el in iter_elements(obj) if pred(el)]


def find_dicts(obj, pred, _depth=0, _out=None):
    """Every dict in a resolved tree (elements' props included) matching pred."""
    out = _out if _out is not None else []
    if _depth > 200:
        return out
    if isinstance(obj, dict):
        if pred(obj):
            out.append(obj)
        for value in obj.values():
            find_dicts(value, pred, _depth + 1, out)
    elif isinstance(obj, list):
        for item in obj:
            find_dicts(item, pred, _depth + 1, out)
    return out


def el_tag(el):
    return el[1] if isinstance(el[1], str) else None


def el_class(el):
    cls = el[3].get("className")
    return cls if isinstance(cls, str) else ""


def has_class(el, fragment):
    return fragment in el_class(el)


def testid(el):
    value = el[3].get("data-testid")
    return value if isinstance(value, str) else ""


def el_text(obj, sep=""):
    """The text an element renders: string children joined, Flight
    placeholders ("$undefined") skipped, surrounding whitespace trimmed."""
    parts = []

    def walk(node, depth=0):
        if depth > 200:
            return
        if isinstance(node, str):
            if node != "$undefined" and not _REF_RE.match(node):
                parts.append(node)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            parts.append(str(node))
        elif is_element(node):
            props = node[3]
            inner = props.get("dangerouslySetInnerHTML")
            if isinstance(inner, dict) and isinstance(inner.get("__html"), str):
                parts.append(html_text(inner["__html"]) or "")
            walk(props.get("children"), depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
    walk(obj)
    return clean_str(sep.join(parts)) if sep == "" else clean_str(sep.join(p for p in parts if p.strip()))


def el_children(el):
    """An element's children as a flat list of elements / strings."""
    children = el[3].get("children")
    if children is None:
        return []
    if is_element(children):
        return [children]
    if isinstance(children, list):
        flat = []
        for child in children:
            if is_element(child) or isinstance(child, (str, int, float)):
                flat.append(child)
            elif isinstance(child, list):
                flat.extend(c for c in child if is_element(c) or isinstance(c, (str, int, float)))
        return flat
    return [children]


# ---- embedded state (old server pages) ------------------------------------------

def embedded_state(page, name):
    """`window.<name> = {...}` on the old server's pages -> the parsed object
    (None when absent)."""
    marker = f"window.{name}"
    i = (page or "").find(marker)
    if i < 0:
        return None
    j = page.find("=", i + len(marker))
    if j < 0:
        return None
    rest = page[j + 1:].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(rest)
    except ValueError:
        return None
    return value


# ---- product -------------------------------------------------------------------------

def _product_object(tree, slug=None):
    """The product record dict on a product / pricing page: the dict with the
    page's slug that carries the product-only keys."""
    def is_product(d):
        return (clean_str(d.get("slug")) and "name" in d
                and ("awards" in d or "pricingQuotes" in d or "interviews" in d))
    candidates = find_dicts(tree, is_product)
    if slug:
        exact = [d for d in candidates if d.get("slug") == slug or slug in (d.get("previousSlugs") or [])]
        candidates = exact or candidates
    if not candidates:
        return None
    return max(candidates, key=lambda d: len(d))


def _vendor(vendor):
    if not isinstance(vendor, dict):
        return None
    slug = clean_str(vendor.get("slug"))
    return {
        "id": clean_str(vendor.get("id") or vendor.get("_id")),
        "name": clean_str(vendor.get("name")),
        "slug": slug,
        "link": refs.vendor_link(slug) if slug else None,
        "homepage": clean_str(vendor.get("homepage")),
        "logo": _logo(vendor.get("logos"), vendor.get("logo")),
    }


def _category_ref(cat):
    if not isinstance(cat, dict) or not clean_str(cat.get("slug")):
        return None
    return {"name": clean_str(cat.get("name")), "slug": cat["slug"], "link": refs.category_link(cat["slug"])}


def _product_stub(item):
    """A related product (competitor / connector / alternative) -> identity + rating."""
    if not isinstance(item, dict):
        return None
    slug = clean_str(item.get("slug"))
    out = {
        "id": clean_str(item.get("id") or item.get("_id")),
        "name": clean_str(item.get("name")),
        "short_name": clean_str(item.get("shortName")),
        "slug": slug,
        "link": refs.product_link(slug) if slug else None,
        "logo": _logo(item.get("logos"), item.get("logo"), item.get("logoUrl")),
    }
    if "homepage" in item:
        out["homepage"] = clean_str(item.get("homepage"))
    if "description" in item or "html" in item:
        out["description"] = clean_str(item.get("description")) or html_text(item.get("html"))
    if isinstance(item.get("vendor"), dict):
        out["vendor"] = _vendor(item["vendor"])
    if isinstance(item.get("rating"), dict):
        out["rating"] = _rating(item["rating"])
        features = item["rating"].get("featureRatings")
        if isinstance(features, list) and features and isinstance(features[0], dict) and "name" in features[0]:
            out["feature_ratings"] = _feature_scores(features)
    return out


def _edition(edition):
    if not isinstance(edition, dict):
        return None
    terms = edition.get("terms") if isinstance(edition.get("terms"), dict) else {}
    return {
        "name": clean_str(edition.get("name")),
        "price": price(edition.get("price")),
        "period": clean_str(terms.get("period")) or clean_str(edition.get("durationTerms")),
        "unit": clean_str(terms.get("unit")) or clean_str(edition.get("unitTerms")),
        "terms": clean_str(edition.get("otherTerms")),
        "deployment_types": sorted({d["type"] for d in edition.get("deploymentTypes") or []
                                    if isinstance(d, dict) and clean_str(d.get("type"))}) or None,
    }


def _starting_price(value):
    if not isinstance(value, dict):
        return None
    amount = number(value.get("price"))
    if amount is None:
        return None
    terms = value.get("terms") if isinstance(value.get("terms"), dict) else {}
    return {"amount": amount, "currency": "USD", "period": clean_str(terms.get("period")),
            "unit": clean_str(terms.get("unit"))}


def _interview(review):
    """One of the product page's full featured reviews ("interviews")."""
    if not isinstance(review, dict):
        return None
    link = clean_str(review.get("reviewLink"))
    sections = []
    for section in review.get("sections") or []:
        if not isinstance(section, dict):
            continue
        responses = [{"question": clean_str(r.get("question")), "answer": html_text(r.get("answer")) if isinstance(r.get("answer"), str) else r.get("answer"),
                      "type": clean_str(r.get("type"))}
                     for r in section.get("responses") or [] if isinstance(r, dict) and clean_str(r.get("question"))]
        if responses:
            sections.append({"title": clean_str(section.get("title")), "responses": responses})
    return {
        "id": clean_str(review.get("id")),
        "slug": link.rsplit("/", 1)[-1] if link else None,
        "link": absolute(link),
        "title": clean_str(review.get("reviewTitle")),
        "rating": number(review.get("rating")),
        "published_date": iso_date(review.get("date")),
        "source": _source(review.get("source")),
        "reviewer": _reviewer(review.get("reviewer")),
        "sections": sections,
    }


def parse_product(page, slug=None):
    """/products/<slug> -> the product record (everything but the pricing
    page's extras, parse_pricing). None when the page carries no product."""
    tree = flight_tree(page)
    p = _product_object(tree, slug)
    if not p:
        return None
    canonical = p["slug"]
    install = p.get("industryInstallShare") if isinstance(p.get("industryInstallShare"), dict) else None
    videos = p.get("vendorVideos") if isinstance(p.get("vendorVideos"), dict) else {}
    pros_cons = p.get("prosAndCons") if isinstance(p.get("prosAndCons"), dict) else {}
    certifications = p.get("certifications") if isinstance(p.get("certifications"), dict) else {}
    true_award = certifications.get("trueAward") if isinstance(certifications.get("trueAward"), dict) else {}
    verified = p.get("customerVerified") if isinstance(p.get("customerVerified"), dict) else {}
    links = p.get("links") if isinstance(p.get("links"), dict) else {}
    cta = links.get("backlinkCta") if isinstance(links.get("backlinkCta"), dict) else {}
    return {
        "id": clean_str(p.get("id")),
        "name": clean_str(p.get("name")),
        "short_name": clean_str(p.get("shortName")),
        "slug": canonical,
        "link": refs.product_link(canonical),
        "reviews_link": refs.product_reviews_link(canonical),
        "logo": _logo(p.get("logos")),
        "homepage": clean_str(p.get("homepage")),
        "pricing_link": clean_str(p.get("pricingUrl")),
        "vendor_cta": {"text": clean_str(cta.get("text")), "link": clean_str(cta.get("url"))} if clean_str(cta.get("url")) else None,
        "vendor": _vendor(p.get("vendor")),
        "description": clean_str(p.get("description")) or html_text(p.get("html")),
        "description_html": clean_str(p.get("html")),
        "previous_slugs": [s for s in p.get("previousSlugs") or [] if clean_str(s)],
        "primary_category": _category_ref(p.get("primaryCategory")),
        "categories": [c for c in (_category_ref(c) for c in p.get("categories") or []) if c],
        "rating": _rating(p.get("rating")),
        "awards": [a for a in (_award(a) for a in p.get("awards") or []) if a],
        "is_vendor_verified": bool(verified.get("verified")) if verified else False,
        "has_true_badge": bool(true_award.get("enabled")) if true_award else False,
        "feature_ratings": _feature_scores(p.get("featureRatings")),
        "pros": [s for s in pros_cons.get("pros") or [] if clean_str(s)],
        "cons": [s for s in pros_cons.get("cons") or [] if clean_str(s)],
        "faq": [{"question": clean_str(f.get("question")), "answer": html_text(f.get("answer"))}
                for f in p.get("faq") or [] if isinstance(f, dict) and clean_str(f.get("question"))],
        "screenshots": [{"link": s["url"], "description": clean_str(s.get("description"))}
                        for s in p.get("screenshots") or [] if isinstance(s, dict) and clean_str(s.get("url"))],
        "videos": [{
            "title": clean_str(v.get("name")), "description": clean_str(v.get("description")),
            "link": clean_str(v.get("url")), "embed_link": clean_str(v.get("embedUrl")),
            "thumbnail": clean_str(v.get("thumbnailUrl")), "upload_date": iso_date(v.get("uploadDate")),
            "duration_seconds": number(v.get("duration")),
        } for v in videos.get("files") or [] if isinstance(v, dict) and clean_str(v.get("url"))],
        "demos": [{
            "type": clean_str(d.get("demoType")), "service": clean_str(d.get("service")),
            "title": clean_str(d.get("title")), "link": clean_str(d.get("url")),
            "thumbnail": clean_str(d.get("thumbnailUrl")),
        } for d in (p.get("productDemos") if isinstance(p.get("productDemos"), list) else []) if isinstance(d, dict) and clean_str(d.get("url"))],
        "operating_systems": [s for s in p.get("operatingSystems") or [] if clean_str(s)],
        "integrations": [s for s in (_product_stub(c) for c in p.get("connectors") or []) if s and s.get("slug")],
        "competitors": [s for s in (_product_stub(c) for c in p.get("competitors") or []) if s and s.get("slug")],
        "industry_install_share": {
            "total_installs": number(install.get("totalInstalls")),
            "last_updated": iso_date(install.get("lastUpdated")),
            "industries": [{
                "naics_code": clean_str(i.get("naicsCode")),
                "slug": refs.INDUSTRY_BY_NAICS.get(str(i.get("naicsCode"))),
                "name": clean_str(i.get("naicsName")),
                "company_count": number(i.get("companyCount")),
                "share_percent": number(i.get("installSharePct")),
            } for i in install.get("industries") or [] if isinstance(i, dict)],
        } if install else None,
        "featured_reviews": [r for r in (_interview(r) for r in p.get("interviews") or []) if r],
    }


def parse_pricing(page, slug=None):
    """/products/<slug>/pricing -> the pricing slice (editions, offerings,
    support, quotes, alternatives) plus the full rating object (the only
    place the product's trScore and the written / quick split appear)."""
    tree = flight_tree(page)
    p = _product_object(tree, slug)
    if not p:
        return None
    support = p.get("support") if isinstance(p.get("support"), dict) else {}
    long_form = p.get("longFormContent") if isinstance(p.get("longFormContent"), dict) else {}
    author = long_form.get("author") if isinstance(long_form.get("author"), dict) else {}
    quotes = []
    for q in p.get("pricingQuotes") or []:
        if not isinstance(q, dict) or not clean_str(q.get("text")):
            continue
        review_slug = clean_str(q.get("reviewSlug"))
        reviewer = _reviewer(q.get("reviewer")) or {}
        quotes.append({
            "text": html_text(q["text"]),
            "rating": number(q.get("rating")),
            "review_link": refs.review_link(review_slug) if review_slug else None,
            "review_date": iso_date(q.get("reviewDate")),
            "source": _source(q.get("sourcing")),
            "reviewer": {
                "name": clean_str(q.get("author")) if clean_str(q.get("author")) not in (None, "Anonymous Reviewer") else reviewer.get("name"),
                "title": clean_str(q.get("role")) or reviewer.get("title"),
                "company": clean_str(q.get("company")) or reviewer.get("company"),
                "is_public": reviewer.get("is_public"),
            },
        })
    alternatives = []
    for alt in p.get("pricingAlternatives") or []:
        stub = _product_stub(alt)
        if not stub or not stub.get("slug"):
            continue
        stub["has_free_version"] = bool(alt.get("freeAvailable")) if alt.get("freeAvailable") is not None else None
        stub["editions"] = [e for e in (_edition(e) for e in alt.get("editionPricing") or []) if e and e["name"]]
        alternatives.append(stub)
    return {
        "slug": p["slug"],
        "rating": _rating(p.get("rating")),
        "starting_price": _starting_price(p.get("startingPrice")),
        "has_free_version": bool(p.get("freeAvailable")) if p.get("freeAvailable") is not None else None,
        "has_free_trial": bool(p.get("trialAvailable")) if p.get("trialAvailable") is not None else None,
        "deployment_types": sorted({d["type"] for d in p.get("deploymentTypes") or []
                                    if isinstance(d, dict) and clean_str(d.get("type"))}),
        "editions": [e for e in (_edition(e) for e in p.get("editionPricing") or []) if e and e["name"]],
        "support": {
            "free_channels": [s for s in support.get("channelsFree") or [] if clean_str(s)],
            "paid_channels": [s for s in support.get("channelsPaid") or [] if clean_str(s)],
        } if support else None,
        "notes": clean_str(p.get("miscPricingInfo")),
        "pricing_link": clean_str(p.get("pricingUrl")),
        "operating_systems": [s for s in p.get("operatingSystems") or [] if clean_str(s)],
        "quotes": quotes,
        "alternatives": alternatives,
        "editorial": {
            "title": clean_str(long_form.get("title")),
            "content": html_text(long_form.get("content")),
            "author": " ".join(part for part in (clean_str(author.get("firstName")), clean_str(author.get("lastName"))) if part) or None,
        } if clean_str(long_form.get("content")) else None,
    }


# ---- reviews list ------------------------------------------------------------------

_CARD_SECTIONS = {
    "use cases and deployment scope": "use_cases",
    "pros": "pros",
    "cons": "cons",
    "likelihood to recommend": "likelihood_to_recommend",
    "return on investment": "return_on_investment",
    "alternatives considered": "alternatives_considered",
    "other software used": "other_software_used",
}


def _card_answer(block):
    """One ReviewAnswer block: the <h3> heading and either a bullet list
    component ({items, type}) or an HTML body."""
    heading, items, body = None, None, []
    for el in iter_elements(block):
        props = el[3]
        if props.get("as") == "h3" and heading is None:
            heading = el_text(el)
        elif isinstance(props.get("items"), list) and props.get("type") in ("pros", "cons"):
            items = [clean_str(i) for i in props["items"] if clean_str(i)]
        inner = props.get("dangerouslySetInnerHTML")
        if isinstance(inner, dict) and isinstance(inner.get("__html"), str):
            text = html_text(inner["__html"])
            if text:
                body.append(text)
    return heading, (items if items is not None else ("\n".join(body) or None))


def _review_card(article, key):
    """One review <article> on a reviews page -> the review summary."""
    props = article[3]
    title, link, rating, badges, published, reviewer, flags = None, None, None, None, None, None, {}
    sections, extra_sections, years = {}, [], None
    for el in iter_elements(article):
        p = el[3]
        if el_tag(el) == "a" and isinstance(p.get("href"), str) and p["href"].startswith("/reviews/") and "#" not in p["href"] and link is None:
            link, title = p["href"], el_text(el)
        elif isinstance(p.get("id"), str) and p["id"].endswith("_rating") and "value" in p:
            rating = number(p.get("value"))
        elif "trusted" in p and "source" in p and "incentive" in p and badges is None:
            badges = _source(p)
        elif el_tag(el) == "time" and isinstance(p.get("dateTime"), str):
            published = p["dateTime"]
        elif isinstance(p.get("reviewer"), dict) and reviewer is None:
            reviewer = _reviewer(p["reviewer"])
        elif "isVetted" in p and "isVerified" in p:
            flags = p
        elif has_class(el, "ReviewAnswer_reviewAnswer") and "proOrCon" not in el_class(el).split(" ")[0] and el_tag(el) == "div" and "ReviewAnswer_reviewAnswer__html" not in el_class(el):
            heading, answer = _card_answer(el)
            if heading and answer is not None:
                key_name = _CARD_SECTIONS.get(heading.lower())
                if key_name and key_name not in sections:
                    sections[key_name] = answer
                elif not key_name:
                    extra_sections.append({"title": heading, "answer": answer})
        elif isinstance(p.get("children"), str) and p["children"].endswith("of experience"):
            years = number(p["children"])
    slug = link.rsplit("/", 1)[-1] if link else None
    if reviewer is not None and years is not None and reviewer.get("years_of_experience") is None:
        reviewer["years_of_experience"] = years
    return {
        "id": key if isinstance(key, str) and refs.HEX_ID_RE.match(key) else None,
        "slug": slug,
        "link": absolute(link),
        "title": title,
        "rating": rating,
        "published_date": iso_date(published),
        "source": badges,
        "use_cases": sections.get("use_cases"),
        "pros": sections.get("pros") if isinstance(sections.get("pros"), list) else ([sections["pros"]] if sections.get("pros") else []),
        "cons": sections.get("cons") if isinstance(sections.get("cons"), list) else ([sections["cons"]] if sections.get("cons") else []),
        "likelihood_to_recommend": sections.get("likelihood_to_recommend"),
        "return_on_investment": sections.get("return_on_investment"),
        "alternatives_considered": sections.get("alternatives_considered"),
        "other_sections": extra_sections,
        "reviewer": reviewer,
        "is_verified_user": bool(flags.get("isVerified")) if flags else None,
        "is_vetted": bool(flags.get("isVetted")) if flags else None,
        "is_reseller": bool(flags.get("isReseller")) if flags else None,
    }


def _facets(raw):
    """The reviews page's facet counts -> named buckets."""
    if not isinstance(raw, dict):
        return None
    stars = [{"stars": number(f.get("value")), "count": number(f.get("count"))}
             for f in raw.get("starRating") or [] if isinstance(f, dict)]
    sizes = [{"company_size": clean_str(f.get("value")), "count": number(f.get("count"))}
             for f in raw.get("companySizeGroup") or [] if isinstance(f, dict)]
    industries = {}
    for f in raw.get("industryCode") or []:
        if not isinstance(f, dict):
            continue
        industry = refs.industry_for_tr_code(f.get("value"))
        key = industry["slug"] if industry else f"code-{f.get('value')}"
        row = industries.setdefault(key, {"slug": industry["slug"] if industry else None,
                                          "name": industry["name"] if industry else None,
                                          "count": 0, "site_codes": []})
        row["count"] += number(f.get("count")) or 0
        row["site_codes"].append(clean_str(str(f.get("value"))))
    countries = [{"country": clean_str(f.get("value")), "count": number(f.get("count"))}
                 for f in raw.get("reviewerCountry") or [] if isinstance(f, dict)]
    return {
        "stars": sorted(stars, key=lambda r: -(r["stars"] or 0)),
        "company_sizes": sizes,
        "industries": sorted(industries.values(), key=lambda r: -r["count"]),
        "countries": countries,
    }


def _hero_product(tree):
    """The ProductHero component's `product` prop on a reviews page."""
    heroes = find_dicts(tree, lambda d: isinstance(d.get("product"), dict) and clean_str(d["product"].get("slug"))
                        and "pageType" in d)
    if not heroes:
        return None
    p = heroes[0]["product"]
    slug = p["slug"]
    return {
        "id": clean_str(p.get("id")),
        "name": clean_str(p.get("name")),
        "short_name": clean_str(p.get("shortName")),
        "slug": slug,
        "link": refs.product_link(slug),
        "logo": _logo(p.get("logos")),
        "homepage": clean_str(p.get("homepage")),
        "vendor": _vendor(p.get("vendor")),
        "primary_category": _category_ref(p.get("primaryCategory")),
        "rating": _rating(p.get("rating")),
    }


def parse_reviews_page(page):
    """/products/<slug>/reviews[?filters] -> {product, total_reviews, page,
    total_pages, facets, reviews}. A page past the end has 0 reviews."""
    tree = flight_tree(page)
    product = _hero_product(tree)
    meta = find_dicts(tree, lambda d: "facets" in d and "totalReviews" in d)
    pages = find_dicts(tree, lambda d: "currentPage" in d and "totalPages" in d and len(d) <= 3)
    reviews, seen = [], set()
    for el in iter_elements(tree):
        # the article's parent element is keyed by the review id
        children = el[3].get("children")
        candidates = [children] if is_element(children) else (children if isinstance(children, list) else [])
        for child in candidates:
            if is_element(child) and el_tag(child) == "article" and has_class(child, "Review_review"):
                card = _review_card(child, el[2])
                if card["slug"] and card["slug"] not in seen:
                    seen.add(card["slug"])
                    reviews.append(card)
    return {
        "product": product,
        "total_reviews": number(meta[0].get("totalReviews")) if meta else None,
        "page": number(pages[0].get("currentPage")) if pages else None,
        "total_pages": number(pages[0].get("totalPages")) if pages else None,
        "facets": _facets(meta[0].get("facets")) if meta else None,
        "reviews": reviews,
    }


def parse_insights_glimpse(page):
    """The "Insights from <product> reviewers" card on a reviews page (plain
    server-rendered HTML, not in the Flight payload): overview paragraphs,
    pros / cons bullets and the HG Insights install count. None when absent."""
    from bs4 import BeautifulSoup
    marker = 'data-testid="review-insights-ai-v3-glimpse"'
    i = (page or "").find(marker)
    if i < 0:
        return None
    start = page.rfind("<section", 0, i)
    end = page.find('data-testid="review-insights-ai-v3-glimpse-cta"', i)
    snippet = page[start:end if end > 0 else i + 60000]
    soup = BeautifulSoup(snippet, "html.parser")

    def text(sel):
        node = soup.select_one(sel)
        return clean_str(node.get_text(" ", strip=True)) if node else None

    def bullets(testid_value):
        box = soup.find(attrs={"data-testid": testid_value})
        if not box:
            return []
        return [clean_str(li.get_text(" ", strip=True)) for li in box.find_all("li") if clean_str(li.get_text(" ", strip=True))]

    overview_card = soup.find(attrs={"data-testid": "review-insights-ai-v3-glimpse-overview"})
    paragraphs, meta_text = [], None
    if overview_card:
        for p in overview_card.find_all("p"):
            cls = " ".join(p.get("class") or [])
            value = clean_str(p.get_text(" ", strip=True))
            if "overviewBody" in cls and value:
                paragraphs.append(value)
            elif "overviewMeta" in cls:
                meta_text = value
    based_on = text("p[class*='insightOverviewCard__subtitle']")
    install_subtitle = text("p[class*='reviewInsightsAiV3Glimpse__subtitle']")
    synthesized_from, last_published = None, None
    if meta_text:
        m = re.search(r"from\s+([\d,]+)\s+reviews", meta_text)
        synthesized_from = number(m.group(1)) if m else None
        m = re.search(r"Last Published\s+(.+)$", meta_text)
        if m:
            try:
                last_published = datetime.strptime(m.group(1).strip(), "%B %d, %Y").date().isoformat()
            except ValueError:
                last_published = clean_str(m.group(1))
    chips = []
    for a in soup.select("[data-testid^='review-insights-ai-v3-glimpse-chips-']"):
        label = clean_str(a.get_text(" ", strip=True))
        if label and label != "Overall":
            chips.append({"name": label, "link": absolute(a.get("href"))})
    if not paragraphs and not bullets("insight-overview-card-pros"):
        return None
    m = re.search(r"([\d,]+)\s+verified reviews", based_on or "")
    return {
        "title": text("[class*='insightOverviewCard__title']"),
        "based_on_reviews": number(m.group(1)) if m else None,
        "based_on": based_on,
        "synthesized_from_reviews": synthesized_from,
        "last_published": last_published,
        "overview": paragraphs,
        "pros": bullets("insight-overview-card-pros"),
        "cons": bullets("insight-overview-card-cons"),
        "hg_insights_installs": number(re.search(r"([\d,]+)\s+HG Insights", install_subtitle or "").group(1))
        if re.search(r"([\d,]+)\s+HG Insights", install_subtitle or "") else None,
        "industry_segments": chips,
    }


# ---- one review ------------------------------------------------------------------------

_MUSTACHE_SECTION_RE = re.compile(r"\{\{([#^])product\}\}(.*?)\{\{/product\}\}", re.S)
_MUSTACHE_VAR_RE = re.compile(r"\{\{(\w+)\}\}")
_KEY_INSIGHTS = {"valueprice": "is_worth_the_price", "features": "has_the_needed_features",
                 "salesmarketing": "lived_up_to_sales_and_marketing", "implementation": "implementation_went_as_expected",
                 "buyagain": "would_buy_again"}


def _render_public_question(template, product):
    """The site's mustache-lite question text: "{{#product}}{{shortName}} Feature
    Ratings{{/product}}{{^product}}Feature Ratings{{/product}}" with the product
    names filled in."""
    if not isinstance(template, str):
        return None
    names = {"name": (product or {}).get("name") or "", "shortName": (product or {}).get("shortName") or (product or {}).get("name") or ""}

    def section(match):
        return match.group(2) if match.group(1) == "#" else ""
    text = _MUSTACHE_SECTION_RE.sub(section, template)
    text = _MUSTACHE_VAR_RE.sub(lambda m: names.get(m.group(1), ""), text)
    return clean_str(text)


def _question_text(question, product):
    for key in ("publicQuestion", "question", "title"):
        value = question.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and clean_str(item.get("text")):
                    rendered = _render_public_question(item["text"], product)
                    if rendered:
                        return rendered
        elif isinstance(value, str) and clean_str(value):
            rendered = _render_public_question(value, product)
            if rendered:
                return rendered
    obj = question.get("object") if isinstance(question.get("object"), dict) else {}
    return _question_text(obj, product) if obj and obj is not question else None


def _answer(kind, values, response, features_by_id):
    """A response's `values` by question type -> a plain JSON answer."""
    if kind in ("text",):
        return html_text(values[0]) if values and isinstance(values[0], str) else None
    if kind in ("bullets", "competitors"):
        return [html_text(v) for v in values if isinstance(v, str) and clean_str(v)]
    if kind == "slider":
        return number(values[0]) if values else None
    if kind == "features":
        out = []
        for item in values:
            if not isinstance(item, dict):
                continue
            score = number(item.get("value"))
            out.append({"feature": features_by_id.get(item.get("featureId")) or item.get("featureId"),
                        "score": score if score else None,
                        "is_not_applicable": bool(item.get("na"))})
        return [o for o in out if o["score"] is not None or o["is_not_applicable"]] or None
    if kind == "multiquestion":
        flags = values[0] if values and isinstance(values[0], dict) else {}
        return {_KEY_INSIGHTS.get(k, k): (v == "yes" if v in ("yes", "no") else v) for k, v in flags.items()}
    if kind == "ratings":
        out = []
        for item in values:
            if isinstance(item, dict) and clean_str(item.get("productName")):
                score = number(item.get("value"))
                out.append({"product_id": clean_str(item.get("productId")), "name": item["productName"],
                            "rating": score if score else None})
        return out or None
    if kind == "likert":
        if all(isinstance(v, str) and v.endswith(":0") for v in values):
            return None
        return values
    if values and all(isinstance(v, str) for v in values):
        return [html_text(v) for v in values if clean_str(v)]
    return values or None


def parse_review(page):
    """/reviews/<slug> -> the full questionnaire. None when the page carries no review."""
    state = embedded_state(page, "__INITIAL_DATA__")
    review = state.get("review") if isinstance(state, dict) else None
    if not isinstance(review, dict) or not clean_str(review.get("slug")):
        return None
    product = review.get("product") if isinstance(review.get("product"), dict) else {}
    vendor = review.get("vendor") if isinstance(review.get("vendor"), dict) else {}
    subject = review.get("subject") if isinstance(review.get("subject"), dict) else {}
    position = subject.get("position") if isinstance(subject.get("position"), dict) else {}
    company = subject.get("company") if isinstance(subject.get("company"), dict) else {}
    industry = company.get("industry") if isinstance(company.get("industry"), dict) else {}
    roles = subject.get("roles") if isinstance(subject.get("roles"), dict) else {}
    location = subject.get("location") if isinstance(subject.get("location"), dict) else {}
    user = subject.get("user") if isinstance(subject.get("user"), dict) else {}
    name_obj = subject.get("name") if isinstance(subject.get("name"), dict) else {}
    rating = review.get("rating") if isinstance(review.get("rating"), dict) else {}
    features_by_id = {}
    for group in review.get("featureGroups") or []:
        if not isinstance(group, dict):
            continue
        for feature in group.get("features") or []:
            if isinstance(feature, dict) and clean_str(feature.get("name")):
                features_by_id[feature.get("_id")] = feature["name"]
    sections = []
    for section in review.get("sections") or []:
        if not isinstance(section, dict):
            continue
        questions = []
        for q in section.get("questions") or []:
            if not isinstance(q, dict):
                continue
            response = q.get("response") if isinstance(q.get("response"), dict) else {}
            values = response.get("values")
            if values in (None, [], "", {}):
                continue
            answer = _answer(clean_str(q.get("type")), values if isinstance(values, list) else [values], response, features_by_id)
            if answer in (None, [], {}):
                continue
            followup = html_text(response.get("followup")) if isinstance(response.get("followup"), str) else None
            questions.append({
                "slug": clean_str(q.get("slug")),
                "question": _question_text(q, product),
                "type": clean_str(q.get("type")),
                "answer": answer,
                "comment": followup,
                "answered_date": iso_datetime(response.get("date")),
            })
        if questions:
            sections.append({"title": clean_str(section.get("publicHeading")) or clean_str(section.get("title")),
                             "questions": questions})
    avatar = clean_str(user.get("pictureUrl"))
    product_slug = clean_str(product.get("slug"))
    vendor_slug = clean_str(vendor.get("slug"))
    is_public = bool(user.get("public")) if user else None
    return {
        "id": clean_str(review.get("_id")),
        "slug": review["slug"],
        "link": refs.review_link(review["slug"]),
        "short_link": clean_str(review.get("purl")),
        "title": clean_str(review.get("heading")),
        "rating": number(rating.get("normalized")),
        "grade": clean_str(review.get("grade")),
        "published_date": iso_date(review.get("publishedDate")),
        "submitted_date": iso_date(review.get("submittedDate")),
        "edited_date": iso_date(review.get("editedDate")),
        "modified_date": iso_date(review.get("modified")),
        "version_reviewed": clean_str(review.get("version")),
        "word_count": number(review.get("wordCount")),
        "status": clean_str(review.get("status")),
        "source": _source(review.get("source")),
        "product": {
            "id": clean_str(product.get("_id")), "name": clean_str(product.get("name")),
            "short_name": clean_str(product.get("shortName")), "slug": product_slug,
            "link": refs.product_link(product_slug) if product_slug else None,
            "rating": _rating(product.get("rating")),
        } if product else None,
        "vendor": {"id": clean_str(vendor.get("_id")), "name": clean_str(vendor.get("name")) or clean_str(review.get("vendorName")),
                   "slug": vendor_slug, "link": refs.vendor_link(vendor_slug) if vendor_slug else None} if vendor or review.get("vendorName") else None,
        "categories": [c for c in (_category_ref(c) for c in review.get("categories") or []) if c],
        "reviewer": {
            "id": clean_str(user.get("_id")),
            "name": (" ".join(p for p in (clean_str(name_obj.get("first")), clean_str(name_obj.get("last"))) if p) or None) if is_public else None,
            "is_public": is_public,
            "title": clean_str(position.get("title")),
            "department": clean_str(position.get("department")),
            "job_type": clean_str(position.get("jobType")),
            "is_current_position": position.get("current") if isinstance(position.get("current"), bool) else None,
            "company": clean_str(company.get("name")),
            "company_size": clean_str(company.get("size")),
            "industry": clean_str(industry.get("name")),
            "country": clean_str(location.get("countryCode")),
            "roles": sorted(k for k, v in roles.items() if v is True),
            "years_of_experience": number(subject.get("yearsExperience")),
            "is_current_user": subject.get("currentExperience") == "current" if subject.get("currentExperience") else None,
            "avatar": absolute(avatar) if avatar and not avatar.endswith("no_photo.png") else None,
            "reputation_score": number((user.get("reputation") or {}).get("score")) if isinstance(user.get("reputation"), dict) else None,
        },
        "sections": sections,
    }


# ---- review insights (AI synthesis) -----------------------------------------------------

def parse_insights(page):
    """/products/<slug>/reviews/review-insights -> per-question syntheses with
    their topics. None when the page carries no synthesis."""
    tree = flight_tree(page)
    roots = find_elements(tree, lambda el: testid(el) == "review-insights-ai-v3-synthesis")
    if not roots:
        return None
    root = roots[0]
    heading = None
    for el in iter_elements(root):
        if el_tag(el) == "h1":
            heading = el_text(el)
            break
    subtitle = None
    for el in iter_elements(root):
        if el_tag(el) == "p" and "__subtitle" in el_class(el):
            subtitle = el_text(el)
            break
    dimensions = []
    for el in iter_elements(root):
        if testid(el).startswith("dimension-tabs-") and el_tag(el) in ("a", "span"):
            dimensions.append({"name": el_text(el), "key": testid(el)[len("dimension-tabs-"):],
                               "link": absolute(el[3].get("href")) if isinstance(el[3].get("href"), str) else None,
                               "is_current": el[3].get("aria-current") == "page"})
    segments = []
    for props in find_dicts(root, lambda d: isinstance(d.get("industries"), list) and "chipPayloads" in d):
        for item in props["industries"]:
            if isinstance(item, dict) and clean_str(item.get("label")):
                segments.append({"id": clean_str(item.get("id")), "name": item["label"],
                                 "link": absolute(item.get("href")), "has_synthesis": bool(item.get("hasSynthesis"))})
        break
    questions = []
    seen = set()
    for section in iter_elements(root):
        if el_tag(section) != "section" or not testid(section).startswith("review-insights-ai-v3-synthesis-question-"):
            continue
        slug = clean_str(section[3].get("data-question-slug")) or testid(section).rsplit("question-", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)
        title, answered, summary, footer, topics = None, None, None, None, []
        for el in iter_elements(section):
            cls = el_class(el)
            if el_tag(el) == "h3" and title is None:
                title = el_text(el)
            elif "__badge" in cls and answered is None:
                answered = number(el_text(el))
            elif el_tag(el) == "p" and "__summary" in cls and summary is None:
                summary = el_text(el)
            elif el_tag(el) == "p" and "__footer" in cls:
                footer = el_text(el)
            elif el_tag(el) == "details" and clean_str(el[3].get("data-topic-slug")):
                name, mentions, body, preview = None, None, None, None
                for sub in iter_elements(el):
                    sub_cls = el_class(sub)
                    if el_tag(sub) == "h4" and name is None:
                        name = el_text(sub)
                    elif "mentionsBadge" in sub_cls and mentions is None:
                        mentions = number(el_text(sub))
                    elif "__summaryText" in sub_cls and body is None:
                        body = el_text(sub)
                    elif "__preview" in sub_cls and preview is None:
                        preview = el_text(sub)
                topics.append({"slug": el[3]["data-topic-slug"], "name": name, "mentions": mentions,
                               "summary": body or preview,
                               "has_synthesis": bool(el[3].get("data-has-synthesis"))})
        questions.append({"slug": slug, "question": title, "answered_count": answered,
                          "summary": summary, "topics": topics, "topics_note": footer})
    m = re.search(r"([\d,]+)\s+verified reviews", subtitle or "")
    return {
        "title": heading,
        "based_on_reviews": number(m.group(1)) if m else None,
        "based_on": subtitle,
        "dimensions": dimensions,
        "industry_segments": segments,
        "questions": questions,
    }


# ---- competitors / alternatives ------------------------------------------------------------

def parse_competitors(page):
    """/products/<slug>/competitors -> {competitors, alternatives: {all, small,
    medium, large}} (the old server's window.__INITIAL_DATA__)."""
    state = embedded_state(page, "__INITIAL_DATA__")
    if not isinstance(state, dict) or "competitors" not in state:
        return None
    segments = state.get("trustmapAlternativesSearch") if isinstance(state.get("trustmapAlternativesSearch"), dict) else {}
    out = {
        "competitors": [s for s in (_product_stub(c) for c in state.get("competitors") or []) if s and s.get("slug")],
        "alternatives": {},
    }
    for segment in refs.ALTERNATIVE_SEGMENTS:
        items = segments.get(segment) if isinstance(segments.get(segment), list) else []
        out["alternatives"][segment] = [s for s in (_product_stub(c) for c in items) if s and s.get("slug")]
    return out


# ---- vendor ----------------------------------------------------------------------------------

def parse_vendor(page):
    """/vendors/<slug> -> the vendor profile + its products (redux vendorPage).
    Contact persons, email domains and the encrypted API key are never
    exposed. None when the page carries no vendor."""
    state = embedded_state(page, "__SERVER_REDUX_STATE__")
    vendor_page = state.get("vendorPage") if isinstance(state, dict) else None
    v = vendor_page.get("vendor") if isinstance(vendor_page, dict) else None
    if not isinstance(v, dict) or not clean_str(v.get("slug")):
        return None
    slug = v["slug"]
    products = []
    for p in vendor_page.get("products") or []:
        stub = _product_stub(p)
        if stub and stub.get("slug"):
            products.append(stub)
    families = []
    for fam in vendor_page.get("productFamilies") or []:
        if isinstance(fam, dict) and clean_str(fam.get("name")):
            families.append({"id": clean_str(fam.get("_id")), "name": fam["name"], "slug": clean_str(fam.get("slug"))})
    return {
        "id": clean_str(v.get("_id")),
        "name": clean_str(v.get("name")),
        "slug": slug,
        "link": refs.vendor_link(slug),
        "logo": _logo(v.get("logos"), v.get("logo")),
        "homepage": clean_str(v.get("homepage")),
        "blog": clean_str(v.get("blog")),
        "description": html_text(v.get("description")),
        "company_size": clean_str(v.get("companySize")),
        "company_type": clean_str(v.get("companyType")),
        "founded": clean_str(v.get("foundingDate")),
        "headquarters": (", ".join(part.strip().rstrip(",") for part in v["headquarters"].split("\n") if part.strip()) or None)
        if isinstance(v.get("headquarters"), str) else None,
        "stock_symbol": clean_str(v.get("stockSymbol")),
        "twitter": clean_str(v.get("twitterId")),
        "linkedin": clean_str(v.get("linkedInId")),
        "keywords": [k for k in v.get("keywords") or [] if clean_str(k)],
        "notable_customers": [c for c in v.get("notableCustomers") or [] if clean_str(c)],
        "is_trustradius_customer": bool(v.get("isCustomer")),
        "awards_count": len(v.get("awards") or []),
        "products_count": len(products),
        "products": products,
        "product_families": families,
        "created_date": iso_date(v.get("created")),
        "modified_date": iso_date(v.get("modified")),
    }


# ---- categories --------------------------------------------------------------------------------

def _category_card(item, position):
    """One product card of a category listing."""
    stub = _product_stub(item)
    if not stub or not stub.get("slug"):
        return None
    pros_cons = item.get("prosAndCons") if isinstance(item.get("prosAndCons"), dict) else {}
    rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
    stub.update({
        "position": position,
        "ranking_score": number(item.get("ranking")),
        "homepage": clean_str(item.get("homepage")),
        "pricing_link": clean_str(item.get("pricingUrl")),
        "description": clean_str(item.get("description")) or html_text(item.get("html")),
        "has_free_trial": bool(item.get("trialAvailable")) if item.get("trialAvailable") is not None else None,
        "starting_price": _starting_price(item.get("startingPrice")),
        "editions_count": len(item.get("editionPricing") or []),
        "awards": [{"type": clean_str(a.get("awardType")), "state": clean_str(a.get("awardState")),
                    "expiration_date": iso_date(a.get("expirationDate"))}
                   for a in item.get("awards") or [] if isinstance(a, dict)],
        "feature_ratings": _feature_scores(rating.get("featureRatings")),
        "pros": [s for s in pros_cons.get("pros") or [] if clean_str(s)],
        "cons": [s for s in pros_cons.get("cons") or [] if clean_str(s)],
    })
    stub["logo"] = stub["logo"] or clean_str(item.get("logoUrl"))
    return stub


def parse_category(page):
    """/categories/<slug>?f=<offset> -> {category, offset, size, total,
    products}. None when the page carries no category listing."""
    tree = flight_tree(page)
    roots = find_dicts(tree, lambda d: isinstance(d.get("initialData"), dict) and isinstance(d.get("category"), dict))
    if not roots:
        return None
    root = roots[0]
    c, init = root["category"], root["initialData"]
    meta = init.get("meta") if isinstance(init.get("meta"), dict) else {}
    offset = number(meta.get("from")) or 0
    products = [card for card in (_category_card(p, offset + i + 1) for i, p in enumerate(init.get("products") or []))
                if card]
    related = []
    for section in find_elements(tree, lambda el: testid(el) == "related-categories"):
        for el in iter_elements(section):
            href = el[3].get("href")
            if isinstance(href, str) and href.startswith("/categories/"):
                slug = href.rsplit("/", 1)[-1]
                if slug and slug not in [r["slug"] for r in related]:
                    related.append({"name": el_text(el), "slug": slug, "link": refs.category_link(slug)})
        break
    overview_html = None
    for el in find_elements(tree, lambda el: testid(el) == "category-overview-card"):
        inner = el[3].get("dangerouslySetInnerHTML")
        if isinstance(inner, dict) and clean_str(inner.get("__html")):
            overview_html = inner["__html"]
            break
    slug = clean_str(c.get("slug"))
    return {
        "category": {
            "id": clean_str(c.get("_id")),
            "name": clean_str(c.get("name")),
            "acronym": clean_str(c.get("acronym")),
            "slug": slug,
            "link": refs.category_link(slug) if slug else None,
            "suffix": clean_str(c.get("suffix")),
            "description": clean_str(c.get("description")),
            "short_description": clean_str(c.get("shortDescription")),
            "overview": html_text(overview_html),
            "overview_html": clean_str(overview_html),
            "product_count": number(c.get("productCount")),
            "is_featured": bool(c.get("featured")),
            "synonyms": [s for s in c.get("synonyms") or [] if clean_str(s)],
            "faq": [{"question": clean_str(f.get("question")), "answer": html_text(f.get("answer"))}
                    for f in c.get("faq") or [] if isinstance(f, dict) and clean_str(f.get("question"))],
            "related_categories": related,
            "videos": [{"service": clean_str(v.get("service")), "link": clean_str(v.get("url")),
                        "thumbnail": clean_str(v.get("thumbnailUrl"))}
                       for v in c.get("videos") or [] if isinstance(v, dict) and clean_str(v.get("url"))],
            "modified_date": iso_date(c.get("modified")),
        },
        "offset": offset,
        "size": number(meta.get("size")) or refs.CATEGORY_PAGE_SIZE,
        "total": number(meta.get("total")),
        "products": products,
    }


def parse_categories_index(page):
    """/categories -> [{group, categories: [...]}] (the whole tree). None when absent."""
    tree = flight_tree(page)
    roots = find_dicts(tree, lambda d: isinstance(d.get("categories"), list) and d["categories"]
                       and isinstance(d["categories"][0], dict) and "children" in d["categories"][0])
    if not roots:
        return None
    groups = []
    for group in roots[0]["categories"]:
        if not isinstance(group, dict):
            continue
        children = []
        for child in group.get("children") or []:
            if not isinstance(child, dict) or not clean_str(child.get("slug")):
                continue
            children.append({
                "id": clean_str(child.get("_id")),
                "name": clean_str(child.get("name")),
                "slug": child["slug"],
                "link": refs.category_link(child["slug"]),
                "description": clean_str(child.get("description")),
                "is_featured": bool(child.get("featured")),
            })
        groups.append({
            "id": clean_str(group.get("_id")),
            "name": clean_str(group.get("name")),
            "slug": clean_str(group.get("slug")),
            "description": clean_str(group.get("description")),
            "categories_count": len(children),
            "categories": children,
        })
    return groups


# ---- compare -----------------------------------------------------------------------------------

def _compare_products(root):
    out = []
    for p in root.get("products") or []:
        if not isinstance(p, dict) or not clean_str(p.get("slug")):
            continue
        out.append({
            "slug": p["slug"], "name": clean_str(p.get("name")), "short_name": clean_str(p.get("shortName")),
            "link": refs.product_link(p["slug"]), "logo": clean_str(p.get("logoUrl")),
            "vendor": {"name": clean_str(p.get("vendorName")), "logo": clean_str(p.get("vendorLogoUrl"))},
            "rating": {"average": number(p.get("averageRating")), "count": number(p.get("reviewCount"))},
        })
    return out


def _compare_overview(slot, slugs):
    rows = {}
    for tr in find_elements(slot, lambda el: el_tag(el) == "tr" and "__row" in el_class(el) and "headRow" not in el_class(el)):
        cells = {}
        for td in find_elements(tr, lambda el: el_tag(el) == "td" and isinstance(el[3].get("data-th"), str)):
            cells[td[3]["data-th"]] = td
        score = None
        for el in iter_elements(tr):
            if testid(el) == "tr-score" and "value" in el[3]:
                score = number(el[3]["value"])
        texts = [el_text(p) for p in find_elements(cells.get("Starting Price", []), lambda el: el_tag(el) == "p")]
        most_used = el_text(cells["Most Used By"]) if "Most Used By" in cells else None
        name = None
        for el in iter_elements(tr):
            if el_tag(el) == "img" and clean_str(el[3].get("alt")):
                name = el[3]["alt"]
                break
        rows[name] = {
            "tr_score": score,
            "most_used_by": None if most_used in (None, "N/A") else most_used,
            "summary": el_text(cells["Product Summary"]) if "Product Summary" in cells else None,
            "starting_price": price(texts[0]) if texts and number(texts[0]) is not None else None,
            "starting_price_terms": texts[1] if len(texts) > 1 else None,
        }
    return rows


def _compare_rows(slot):
    """The <tr data-testid=comparison-row> rows of a slot: (header text, [td cells])."""
    out = []
    for tr in find_elements(slot, lambda el: el_tag(el) == "tr" and (testid(el) == "comparison-row" or "comparisonRow" in el_class(el))):
        header, cells = None, []
        for child in el_children(tr):
            if is_element(child) and el_tag(child) == "th":
                header = el_text(child)
                for comp in iter_elements(child):
                    if not isinstance(comp[1], str) and clean_str(comp[3].get("title")):
                        header = comp[3]["title"]
                        break
            elif is_element(child) and el_tag(child) == "td":
                cells.append(child)
        out.append((header, tr, cells))
    return out


def _cell_product(cell):
    """The product name a cell is headed with (the logo + name span)."""
    for el in iter_elements(cell):
        if "comparisonStackedHeading" in el_class(el) or "StackedHeading" in el_class(el):
            return el_text(el)
    return None


def parse_compare(page):
    """/compare-products/<a>-vs-<b>[-vs-<c>] -> the side-by-side data. None
    when the page carries no comparison."""
    tree = flight_tree(page)
    roots = find_dicts(tree, lambda d: isinstance(d.get("sections"), list) and "productIds" in d and isinstance(d.get("slots"), dict))
    if not roots:
        return None
    root = roots[0]
    products = _compare_products(root)
    slugs = [p["slug"] for p in products]
    names = {p["name"]: p["slug"] for p in products}
    names.update({p["short_name"]: p["slug"] for p in products if p.get("short_name")})
    names.update({p["vendor"]["name"]: p["slug"] for p in products if p["vendor"].get("name")})
    slots = root["slots"]
    footer = root.get("footerSlots") if isinstance(root.get("footerSlots"), dict) else {}

    def slug_for(label):
        if not label:
            return None
        if label in names:
            return names[label]
        for name, slug in names.items():
            if name and (name in label or label in name):
                return slug
        return None

    # overview
    overview = {}
    for label, row in _compare_overview(slots.get("overview", []), slugs).items():
        slug = slug_for(label)
        if slug:
            overview[slug] = row
    # pricing: editions per product (cells in product order) + offerings matrix
    pricing = {slug: {"editions": [], "offerings": {}, "pricing_link": None} for slug in slugs}
    for header, tr, cells in _compare_rows(slots.get("pricing", [])):
        if header and header.lower().startswith("editions"):
            for slug, cell in zip(slugs, cells):
                for row in find_elements(cell, lambda el: "PricingEditions__row" in el_class(el)):
                    name = price_text = terms = None
                    for el in iter_elements(row):
                        if testid(el) == "edition-name":
                            name = el_text(el)
                        elif testid(el) == "edition-price":
                            price_text = el_text(el)
                        elif testid(el) == "edition-terms":
                            terms = el_text(el)
                    if name:
                        pricing[slug]["editions"].append({"name": name, "price": price(price_text), "terms": terms})
        elif header and header.lower().startswith("offerings"):
            label = None
            for el in iter_elements(tr):
                if el_tag(el) == "th" and "__head" in el_class(el) and "headRow" not in el_class(el):
                    label = el_text(el)
                elif el_tag(el) == "tr" and "__valueRow" in el_class(el) and label:
                    for slug, td in zip(slugs, [c for c in el_children(el) if is_element(c) and el_tag(c) == "td"]):
                        value = el_text(td)
                        pricing[slug]["offerings"][label] = (value == "Yes") if value in ("Yes", "No") else value
    for header, tr, cells in _compare_rows(footer.get("pricing", [])):
        for slug, cell in zip(slugs, cells):
            for comp in iter_elements(cell):
                if clean_str(comp[3].get("href")) and comp[3].get("label") == "Pricing Info":
                    pricing[slug]["pricing_link"] = comp[3]["href"]
    # community pulse: "considered both" answers + the key-insight yes/no counts
    community = {"considered_both_products": [], "key_insights": {}}
    for props in find_dicts(slots.get("community-pulse", []), lambda d: isinstance(d.get("answers"), list) and len(d) == 1):
        for a in props["answers"]:
            if not isinstance(a, dict):
                continue
            community["considered_both_products"].append({
                "review_id": clean_str(a.get("id")),
                "product": clean_str(a.get("productName")), "product_slug": slug_for(a.get("productName")),
                "text": html_text(a.get("fullHtml")),
                "source": _source(a.get("source")),
                "reviewer": {"name": clean_str(a.get("displayName")), "title": clean_str(a.get("jobTitle")),
                             "job_type": clean_str(a.get("jobType")), "department": clean_str(a.get("department")),
                             "company": clean_str(a.get("companyName")), "industry": clean_str(a.get("industryType")),
                             "company_size": clean_str(a.get("companySize")), "is_public": bool(a.get("isPublic")),
                             "avatar": absolute(a.get("avatarUrl")) if clean_str(a.get("avatarUrl")) and not str(a.get("avatarUrl")).endswith("no_photo.png") else None,
                             "profile_link": absolute(a.get("profileUrl")) if clean_str(a.get("profileUrl")) else None},
            })
    for props in find_dicts(slots.get("community-pulse", []), lambda d: isinstance(d.get("products"), list) and d["products"]
                            and isinstance(d["products"][0], dict) and "insights" in d["products"][0]):
        for p in props["products"]:
            insights = p.get("insights") if isinstance(p.get("insights"), dict) else {}
            community["key_insights"][p.get("slug")] = {
                _KEY_INSIGHTS.get(k.lower(), k): {"yes": number(v.get("yesCount")), "no": number(v.get("noCount")),
                                                 "no_answer": number(v.get("noneCount"))}
                for k, v in insights.items() if isinstance(v, dict)}
        break
    # features: one component per feature group
    features = []
    seen_groups = set()
    for props in find_dicts(slots.get("features", []), lambda d: isinstance(d.get("features"), list) and "headers" in d and "heading" in d):
        if props.get("id") in seen_groups:
            continue
        seen_groups.add(props.get("id"))
        features.append({
            "group": clean_str(props.get("heading")),
            "slug": clean_str(props.get("id")),
            "group_scores": [{"product_slug": clean_str(h.get("slug")), "score": number(h.get("avg")),
                              "ratings_count": number(h.get("ratingsCount")), "vs_category": clean_str(h.get("delta")),
                              "trend": clean_str(h.get("deltaTrend"))}
                             for h in props.get("headers") or [] if isinstance(h, dict)],
            "features": [{"name": clean_str(f.get("name")),
                          "scores": [{"product_slug": clean_str(c.get("slug")), "score": number(c.get("avg")),
                                      "ratings_count": number(c.get("ratingsCount")), "is_winner": bool(c.get("isWinner"))}
                                     for c in f.get("cells") or [] if isinstance(c, dict)]}
                         for f in props["features"] if isinstance(f, dict) and clean_str(f.get("name"))],
        })
    # best alternatives per segment
    alternatives = []
    for header, tr, cells in _compare_rows(slots.get("best-alternatives", [])):
        picks, seen_slugs = [], set()
        for props in find_dicts(cells, lambda d: "comparedSlugs" in d and clean_str(d.get("slug"))):
            if props["slug"] in seen_slugs:
                continue
            seen_slugs.add(props["slug"])
            picks.append({"slug": props["slug"], "name": clean_str(props.get("productName")),
                          "link": refs.product_link(props["slug"]), "logo": clean_str(props.get("logoUrl")),
                          "score": number(props.get("score"))})
        if header:
            alternatives.append({"segment": header, "products": picks})
    # user ratings: per dimension, one card per product
    user_ratings = []
    for header, tr, cells in _compare_rows(slots.get("user-ratings", [])):
        scores = []
        for slug, cell in zip(slugs, cells):
            score, count = None, None
            for el in iter_elements(cell):
                if testid(el) == "circle-progress-chart-text":
                    score = number(el_text(el))
                elif "__ratings" in el_class(el):
                    count = number(el_text(el))
            scores.append({"product_slug": slug, "score": score, "ratings_count": count})
        slug_key = None
        for comp in iter_elements(tr):
            if not isinstance(comp[1], str) and clean_str(comp[3].get("slug")) and clean_str(comp[3].get("title")):
                slug_key = comp[3]["slug"]
                break
        user_ratings.append({"dimension": header, "slug": slug_key, "scores": scores})
    # testimonials: one quote per product per question
    testimonials = []
    for header, tr, cells in _compare_rows(slots.get("user-testimonials", [])):
        quotes = []
        for slug, cell in zip(slugs, cells):
            comps = find_dicts(cell, lambda d: "hasAnswer" in d)
            if not comps:
                continue
            c = comps[0]
            if not c.get("hasAnswer"):
                quotes.append({"product_slug": slug, "has_answer": False})
                continue
            quotes.append({
                "product_slug": slug, "has_answer": True,
                "text": html_text(c.get("text")) if isinstance(c.get("text"), str) else None,
                "pros": [html_text(x) for x in c["pros"] if isinstance(x, str)] if isinstance(c.get("pros"), list) else None,
                "cons": [html_text(x) for x in c["cons"] if isinstance(x, str)] if isinstance(c.get("cons"), list) else None,
                "bullets": [html_text(x) for x in c["bullets"] if isinstance(x, str)] if isinstance(c.get("bullets"), list) else None,
                "review_title": clean_str(c.get("reviewHeading")),
                "review_link": absolute(c.get("href")),
                "source": _source(c.get("reviewSource")),
                "reviewer": {"name": clean_str(c.get("displayName")), "title": clean_str(c.get("jobTitle")),
                             "is_public": bool(c.get("isPublic")),
                             "avatar": absolute(c.get("avatarUrl")) if clean_str(c.get("avatarUrl")) and not str(c.get("avatarUrl")).endswith("no_photo.png") else None,
                             "profile_link": absolute(c.get("profileUrl")) if clean_str(c.get("profileUrl")) else None},
            })
        if quotes:
            testimonials.append({"question": header, "slug": clean_str(tr[3].get("id")), "quotes": quotes})
    # screenshots per product
    screenshots = {}
    for section in find_elements(tree, lambda el: el_tag(el) == "section" and "comparisonScreenshots" in el_class(el) and "__" not in el_class(el)):
        name = None
        for el in iter_elements(section):
            if el_tag(el) == "h3":
                name = (el_text(el) or "").replace(" Screenshots", "").strip()
                break
        slug = slug_for(name)
        if not slug or slug in screenshots:
            continue
        screenshots[slug] = [{"link": a[3]["href"], "description": next((clean_str(i[3].get("alt")) for i in iter_elements(a) if el_tag(i) == "img"), None)}
                             for a in find_elements(section, lambda el: el_tag(el) == "a" and isinstance(el[3].get("href"), str))]
    sections = [{"id": clean_str(s.get("id")), "heading": clean_str(s.get("heading")), "state": clean_str(s.get("state"))}
                for s in root.get("sections") or [] if isinstance(s, dict)]
    for p in products:
        p["overview"] = overview.get(p["slug"])
        p["pricing"] = pricing.get(p["slug"])
        p["key_insights"] = community["key_insights"].get(p["slug"])
        p["screenshots"] = screenshots.get(p["slug"], [])
    return {
        "link": refs.compare_link(slugs),
        "products": products,
        "sections": sections,
        "considered_both_products": community["considered_both_products"],
        "features": features,
        "best_alternatives": alternatives,
        "user_ratings": user_ratings,
        "testimonials": testimonials,
    }


# ---- JSON --------------------------------------------------------------------------------------

_PATH_LINK = {"product": refs.product_link, "vendor": refs.vendor_link, "category": refs.category_link}


def parse_search(payload, kind="product"):
    """/api/v1/complete -> [{id, name, slug, type, link}] across the groups."""
    out, seen = [], set()
    for group in payload or []:
        if not isinstance(group, dict):
            continue
        group_kind = clean_str(group.get("slug")) or kind
        for item in group.get("options") or []:
            if not isinstance(item, dict) or not clean_str(item.get("slug")):
                continue
            slug = item["slug"]
            if (group_kind, slug) in seen:
                continue
            seen.add((group_kind, slug))
            builder = _PATH_LINK.get(group_kind)
            out.append({
                "id": clean_str(item.get("_id")),
                "name": clean_str(item.get("text")),
                "slug": slug,
                "type": group_kind,
                "link": builder(slug) if builder else absolute(item.get("path")),
            })
    return out


def parse_competitors_api(payload):
    """/api/v1/product-competitors -> [{id, name, slug, link, logo, vendor}]."""
    return [s for s in (_product_stub(item) for item in payload or []) if s and s.get("slug")]
