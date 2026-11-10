"""Offline tests for the TrustRadius parsers against the captured fixtures
(trustradius/fixtures/, 2026-11-07; the list is in parsers.py's docstring).

    python -m pytest trustradius/test_parsers.py -q

Every parser is exercised on a rich page, a sparse page and a not-found /
challenge page. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trustradius import parsers as P  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---- helpers -----------------------------------------------------------------------------------

def test_value_helpers():
    assert P.clean_str("  a  b ") == "a b" and P.clean_str("") is None and P.clean_str(3) is None
    assert P.html_text("Line one<br>Line <b>two</b> &amp; three") == "Line one\nLine two & three"
    assert P.iso_date("2025-11-05T19:21:30.915Z") == "2025-11-05" and P.iso_date("nope") is None
    assert P.iso_datetime("2025-10-22T14:43:14.666Z") == "2025-10-22T14:43:14Z"
    assert P.number("1,718") == 1718 and P.number("8.6") == 8.6 and P.number("x") is None and P.number(True) is None
    assert P.price("$25.00") == {"amount": 25.0, "currency": "USD"}
    assert P.price("$$54") == {"amount": 54, "currency": "USD"}
    assert P.price("49") == {"amount": 49, "currency": "USD"}
    assert P.price("€30") == {"amount": 30, "currency": "EUR"}
    assert P.price("") is None and P.price("Free") is None


def test_flight_text_rows_are_byte_lengths():
    # a 2-byte character in a T row: the length counts bytes, so the next row survives
    payload = '1:T6,héllo\n2:["x"]\n'
    rows = P.flight_rows(payload)
    assert rows["1"] == "héllo" and rows["2"] == ["x"]
    assert P.resolve(["$1", "$$2", "$undefined"], rows) == ["héllo", "$2", None]


def test_embedded_state_missing():
    assert P.embedded_state("<html></html>", "__INITIAL_DATA__") is None
    assert P.embedded_state("window.__X__ = not json;", "__X__") is None


# ---- product ------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def salesforce():
    return P.parse_product(fixture("product_salesforce.html"), "salesforce-agentforce-sales")


@pytest.fixture(scope="module")
def korero():
    return P.parse_product(fixture("product_korero.html"), "korero")


def test_parse_product_identity(salesforce):
    assert salesforce["id"] == "5061d969e1ff5d0200000013"
    assert salesforce["name"] == "Salesforce Agentforce Sales" and salesforce["short_name"] == "Agentforce Sales"
    assert salesforce["slug"] == "salesforce-agentforce-sales"
    assert salesforce["link"] == "https://www.trustradius.com/products/salesforce-agentforce-sales"
    assert salesforce["vendor"]["name"] == "Salesforce" and salesforce["vendor"]["slug"] is None
    assert salesforce["previous_slugs"] == ["salesforce", "sfdc", "salesforce-com", "salesforce-sales-cloud"]
    assert salesforce["primary_category"] == {"name": "Customer Relationship Management (CRM)", "slug": "crm",
                                              "link": "https://www.trustradius.com/categories/crm"}
    assert len(salesforce["categories"]) == 6
    assert salesforce["homepage"] == "https://www.salesforce.com/sales"
    assert salesforce["vendor_cta"]["text"] == "View Demo"


def test_parse_product_ratings_awards_features(salesforce):
    assert salesforce["rating"]["average"] == 8.8 and salesforce["rating"]["count"] == 3472
    assert len(salesforce["awards"]) == 17
    assert salesforce["awards"][0] == {"title": "Top Rated 2022", "type": "toprated", "state": "awarded",
                                       "published_date": "2022-05-11", "expiration_date": "2023-05-11",
                                       "badge": "TopRated-Gradient-2022"}
    assert salesforce["is_vendor_verified"] is True and salesforce["has_true_badge"] is True
    assert len(salesforce["feature_ratings"]) == 31
    first = salesforce["feature_ratings"][0]
    assert first["name"] == "Customer data management / contact management"
    assert first["score"] == 8.6 and first["ratings_count"] == 268 and first["category_average"] == 8.6
    assert first["description"].startswith("The software acts as a single source")
    assert len(salesforce["pros"]) == 10 and len(salesforce["cons"]) == 10
    assert salesforce["faq"][0]["question"] == "What is Agentforce Sales?"


def test_parse_product_media_and_relations(salesforce):
    assert len(salesforce["screenshots"]) == 6 and salesforce["screenshots"][0]["link"].startswith("https://media.trustradius.com/")
    assert len(salesforce["videos"]) == 3 and salesforce["videos"][0]["duration_seconds"] == 301
    assert salesforce["videos"][0]["upload_date"] == "2024-07-18"
    assert len(salesforce["demos"]) == 1 and salesforce["demos"][0]["service"] == "youtube"
    assert len(salesforce["integrations"]) == 57 and salesforce["integrations"][0]["slug"] == "salesforce-agentforce-marketing"
    assert len(salesforce["competitors"]) == 18
    assert salesforce["competitors"][0]["slug"] == "zoho-crm" and salesforce["competitors"][0]["rating"]["count"] == 1038
    share = salesforce["industry_install_share"]
    assert share["total_installs"] == 4998 and share["last_updated"] == "2026-11-06"
    assert share["industries"][0] == {"naics_code": "54", "slug": "professional-services",
                                      "name": "Professional, Scientific, and Technical Services",
                                      "company_count": 1058, "share_percent": 21.2}


def test_parse_product_featured_reviews(salesforce):
    featured = salesforce["featured_reviews"]
    assert len(featured) == 5
    first = featured[0]
    assert first["slug"] == "salesforce-sales-cloud-2025-10-28-02-41-11"
    assert first["link"] == "https://www.trustradius.com/reviews/salesforce-sales-cloud-2025-10-28-02-41-11"
    assert first["rating"] == 9 and first["published_date"] == "2025-11-05"
    assert first["source"] == {"is_trusted": True, "incentive": "TrustRadius", "channel": "CommunityInvite"}
    assert first["reviewer"]["name"] == "Abhinav Chadha" and first["reviewer"]["company_size"] == "501-1000 employees"
    assert first["sections"][0]["title"] == "Overall Satisfaction"
    assert first["sections"][0]["responses"][0]["type"] == "text"


def test_parse_product_sparse(korero):
    assert korero["name"] == "Korero" and korero["rating"] == {"average": 8.9, "count": 4, "tr_score": None,
                                                              "written_reviews": None, "quick_ratings": None}
    assert korero["awards"] == [] and korero["is_vendor_verified"] is False and korero["has_true_badge"] is False
    assert korero["industry_install_share"] is None and korero["demos"] == []
    assert korero["operating_systems"] == ["Windows", "Mac"]
    assert len(korero["featured_reviews"]) == 3 and len(korero["competitors"]) == 3
    assert korero["logo"].startswith("https://media.trustradius.com/product-logos/")


def test_parse_product_not_found_and_challenge():
    assert P.parse_product(fixture("product_notfound.html")) is None
    assert P.parse_product(fixture("cloudflare_challenge.html")) is None
    assert P.parse_pricing(fixture("product_notfound.html")) is None


# ---- pricing -------------------------------------------------------------------------------------

def test_parse_pricing_rich():
    pricing = P.parse_pricing(fixture("product_pricing_salesforce.html"), "salesforce-agentforce-sales")
    assert pricing["rating"]["tr_score"] == 8.816
    assert pricing["rating"]["written_reviews"] == {"average": 8.9, "count": 470, "tr_score": 8.89}
    assert pricing["rating"]["quick_ratings"]["count"] == 3002
    assert pricing["starting_price"] == {"amount": 25, "currency": "USD", "period": "per month", "unit": None}
    assert pricing["has_free_version"] is False and pricing["has_free_trial"] is True
    assert pricing["deployment_types"] == ["saas"]
    assert [e["name"] for e in pricing["editions"]] == ["Starter", "Professional", "Enterprise", "Unlimited", "Agentforce 1 Sales"]
    assert pricing["editions"][0]["price"] == {"amount": 25.0, "currency": "USD"}
    assert pricing["editions"][0]["period"] == "per month" and pricing["editions"][0]["unit"] == "per user"
    assert len(pricing["support"]["free_channels"]) == 7
    assert len(pricing["quotes"]) == 12
    quote = pricing["quotes"][0]
    assert quote["rating"] == 2 and quote["review_date"] == "2023-09-14"
    assert quote["review_link"] == "https://www.trustradius.com/reviews/salesforce-com-2023-09-11-09-02-52"
    assert quote["source"]["channel"] == "CommunityInbound"
    assert len(pricing["alternatives"]) == 3
    assert pricing["alternatives"][0]["slug"] == "capsule-crm" and pricing["alternatives"][0]["rating"]["tr_score"] == 8.858
    assert pricing["alternatives"][0]["has_free_version"] is True
    assert pricing["editorial"] is None


def test_parse_pricing_sparse():
    pricing = P.parse_pricing(fixture("product_pricing_korero.html"), "korero")
    assert pricing["starting_price"] is None
    assert pricing["has_free_version"] is True
    assert pricing["deployment_types"] == ["on-premise", "saas"]
    assert pricing["notes"].startswith("Pricing is computed on a monthly basis")
    assert pricing["operating_systems"] == ["Windows", "Mac"]
    assert [e["price"]["amount"] for e in pricing["editions"]] == [10.0, 22.0]


# ---- reviews list --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def reviews_p1():
    return P.parse_reviews_page(fixture("reviews_salesforce_p1.html"))


def test_parse_reviews_page_header(reviews_p1):
    assert reviews_p1["product"]["slug"] == "salesforce-agentforce-sales"
    assert reviews_p1["product"]["rating"] == {"average": 8.8, "count": 3472, "tr_score": None,
                                               "written_reviews": None, "quick_ratings": None}
    assert reviews_p1["total_reviews"] == 470 and reviews_p1["page"] == 1 and reviews_p1["total_pages"] == 47
    facets = reviews_p1["facets"]
    assert facets["stars"][0] == {"stars": 5, "count": 285}
    assert {f["company_size"]: f["count"] for f in facets["company_sizes"]} == {"medium": 252, "large": 123, "small": 95}
    assert facets["industries"][0]["slug"] == "information" and facets["industries"][0]["count"] == 145
    assert facets["countries"][0] == {"country": "USA", "count": 200}


def test_parse_reviews_page_cards(reviews_p1):
    reviews = reviews_p1["reviews"]
    assert len(reviews) == 10 and len({r["slug"] for r in reviews}) == 10
    first = reviews[0]
    assert first["id"] == "698ca52593ce28d48a43b3a3"
    assert first["slug"] == "salesforce-sales-cloud-2026-02-11-09-49-56"
    assert first["link"] == "https://www.trustradius.com/reviews/salesforce-sales-cloud-2026-02-11-09-49-56"
    assert first["title"] == "All-in-one CRM for better sales performance"
    assert first["rating"] == 8 and first["published_date"] == "2026-02-16"
    assert first["source"] == {"is_trusted": True, "incentive": "TrustRadius", "channel": "CommunityInvite"}
    assert first["use_cases"].startswith("There are multiple ways") and "\n" in first["use_cases"]
    assert len(first["pros"]) == 3 and len(first["cons"]) == 3
    assert first["likelihood_to_recommend"].startswith("1. It is best for organizations")
    assert first["reviewer"]["name"] == "Tripti Kashaudhan" and first["reviewer"]["years_of_experience"] == 2
    assert first["reviewer"]["is_linkedin_verified"] is True
    assert first["is_vetted"] is True and first["is_verified_user"] is False and first["is_reseller"] is False
    assert first["other_sections"] == []


def test_parse_reviews_page_variants():
    page2 = P.parse_reviews_page(fixture("reviews_hubspot_p2.html"))
    assert page2["page"] == 2 and page2["total_pages"] == 177 and page2["total_reviews"] == 1764
    assert page2["product"]["slug"] == "hubspot-crm" and len(page2["reviews"]) == 10
    industry = P.parse_reviews_page(fixture("reviews_hubspot_industry.html"))
    assert industry["total_reviews"] == 142 and industry["total_pages"] == 15
    sparse = P.parse_reviews_page(fixture("reviews_korero.html"))
    assert sparse["total_reviews"] == 3 and len(sparse["reviews"]) == 3
    assert sparse["page"] is None and sparse["total_pages"] is None   # no pager under 10 reviews
    past_end = P.parse_reviews_page(fixture("reviews_hubspot_past_end.html"))
    assert past_end["reviews"] == [] and past_end["page"] == 178 and past_end["total_pages"] == 177
    challenge = P.parse_reviews_page(fixture("cloudflare_challenge.html"))
    assert challenge["product"] is None and challenge["reviews"] == []


def test_parse_insights_glimpse():
    glimpse = P.parse_insights_glimpse(fixture("reviews_salesforce_p1.html"))
    assert glimpse["title"] == "Insights from Agentforce Sales Reviewers"
    assert glimpse["based_on_reviews"] == 36 and glimpse["synthesized_from_reviews"] == 36
    assert glimpse["last_published"] == "2026-05-27"
    assert len(glimpse["overview"]) == 2 and glimpse["overview"][0].startswith("Salesforce Sales Cloud functions")
    assert glimpse["pros"][0] == "Extensive customization options for unique workflows"
    assert len(glimpse["cons"]) == 5
    assert glimpse["hg_insights_installs"] == 4998
    assert glimpse["industry_segments"][0]["name"] == "Professional, Scientific, and Technical Services"
    assert P.parse_insights_glimpse(fixture("reviews_korero.html")) is None
    assert P.parse_insights_glimpse(fixture("cloudflare_challenge.html")) is None


# ---- one review ----------------------------------------------------------------------------------

def test_parse_review_full():
    review = P.parse_review(fixture("review_salesforce_full.html"))
    assert review["id"] == "69007397a310025b5146e346"
    assert review["slug"] == "salesforce-sales-cloud-2025-10-28-02-41-11"
    assert review["rating"] == 9 and review["grade"] == "A"
    assert review["published_date"] == "2025-11-05" and review["submitted_date"] == "2025-10-28"
    assert review["version_reviewed"] == "Enterprise" and review["word_count"] == 448
    assert review["source"] == {"is_trusted": True, "incentive": "TrustRadius", "channel": "CommunityInvite"}
    assert review["product"]["slug"] == "salesforce-agentforce-sales"
    assert review["vendor"]["link"] == "https://www.trustradius.com/vendors/salesforce"
    reviewer = review["reviewer"]
    assert reviewer["name"] == "Abhinav Chadha" and reviewer["is_public"] is True
    assert reviewer["company"] == "Ksolves India Limited" and reviewer["industry"] == "Information Technology & Services"
    assert reviewer["country"] == "IND" and reviewer["years_of_experience"] == 8
    assert reviewer["roles"] == ["consultant", "decisionMaker", "implementer", "reseller", "support", "user"]
    assert "email" not in json.dumps(review)        # never exposed
    sections = {s["title"]: {q["slug"]: q for q in s["questions"]} for s in review["sections"]}
    overall = sections["Overall Satisfaction with Salesforce Sales Cloud"]
    assert overall["product-usage"]["type"] == "text" and overall["product-usage"]["answer"].startswith("I’m using Sales Cloud")
    assert overall["product-usage"]["question"] == "Use Cases and Deployment Scope"
    assert len(overall["things-done-well"]["answer"]) == 2 and len(overall["things-done-poorly"]["answer"]) >= 1
    assert overall["likelihood-to-recommend"]["answer"] == 9
    assert overall["likelihood-to-recommend"]["comment"].startswith("Obviously, for any business")
    assert overall["alternatives-evaluated"]["answer"] == ["Odoo"]
    assert overall["quick-pulse"]["answer"] == {"is_worth_the_price": True, "has_the_needed_features": True,
                                                "lived_up_to_sales_and_marketing": True,
                                                "implementation_went_as_expected": True, "would_buy_again": True}
    assert overall["other-software-used"]["answer"][0]["name"] == "Salesforce Service Cloud"
    assert "feature-ratings" not in overall           # every feature left at 0 = unanswered
    assert sections["Using Salesforce Sales Cloud"]["product-usability"]["answer"] == 9


def test_parse_review_sparse_and_not_found():
    review = P.parse_review(fixture("review_salesforce_sparse.html"))
    assert review["slug"] == "salesforce-sales-cloud-2025-10-22-09-42-29"
    assert review["rating"] == 10 and review["grade"] == "C"
    assert review["reviewer"]["name"] == "Puneet Khubchandani"
    assert review["reviewer"]["avatar"] is None     # no_photo placeholder
    assert [q["slug"] for s in review["sections"] for q in s["questions"]] == [
        "product-usage", "things-done-well", "things-done-poorly", "likelihood-to-recommend",
        "operational-benefits", "scaleability-rating", "quick-pulse"]
    assert P.parse_review(fixture("review_notfound.html")) is None
    assert P.parse_review(fixture("cloudflare_challenge.html")) is None


# ---- insights ------------------------------------------------------------------------------------

def test_parse_insights():
    insights = P.parse_insights(fixture("insights_salesforce.html"))
    assert insights["title"] == "Insights from Agentforce Sales Reviewers"
    assert insights["based_on_reviews"] == 36
    assert [d["key"] for d in insights["dimensions"]] == ["industry", "company-size", "country", "department"]
    assert insights["dimensions"][0]["is_current"] is True
    assert insights["industry_segments"][0]["id"] == "professional-services"
    questions = {q["slug"]: q for q in insights["questions"]}
    assert len(questions) == 6
    roi = questions["operational-benefits"]
    assert roi["question"].startswith("What positive or negative impact")
    assert roi["answered_count"] == 36 and len(roi["topics"]) == 5
    assert roi["topics"][0] == {"slug": "increased-revenue-and-sales", "name": "Increased Revenue and Sales",
                                "mentions": 7, "summary": roi["topics"][0]["summary"], "has_synthesis": True}
    assert roi["topics"][0]["summary"].startswith("A notable portion of reviewers")
    assert roi["summary"].startswith("Salesforce Sales Cloud has largely demonstrated")
    assert roi["topics_note"] == "Showing top 5 topics"
    assert P.parse_insights(fixture("reviews_salesforce_p1.html")) is None
    assert P.parse_insights(fixture("cloudflare_challenge.html")) is None


# ---- competitors ---------------------------------------------------------------------------------

def test_parse_competitors():
    record = P.parse_competitors(fixture("competitors_salesforce.html"))
    assert len(record["competitors"]) == 9
    first = record["competitors"][0]
    assert first["slug"] == "zendesk-support-suite" and first["vendor"]["slug"] == "zendesk"
    assert first["rating"]["average"] == 8.5 and first["rating"]["written_reviews"]["count"] == 225
    assert first["feature_ratings"][0]["name"] == "Organize and prioritize service tickets"
    assert {k: len(v) for k, v in record["alternatives"].items()} == {"all": 10, "small": 10, "medium": 10, "large": 10}
    small = record["alternatives"]["small"][0]
    assert small["slug"] == "salesflare" and small["rating"]["average"] == 10 and small["description"].startswith("Salesflare")
    sparse = P.parse_competitors(fixture("competitors_korero.html"))
    assert len(sparse["competitors"]) == 10
    assert P.parse_competitors(fixture("product_notfound.html")) is None
    assert P.parse_competitors(fixture("cloudflare_challenge.html")) is None


def test_parse_competitors_api():
    items = P.parse_competitors_api(fixture("competitors_api_hubspot.json"))
    assert len(items) == 15
    assert items[0]["slug"] == "salesforce-agentforce-sales" and items[0]["vendor"]["slug"] == "salesforce"
    assert P.parse_competitors_api([]) == []


# ---- vendor --------------------------------------------------------------------------------------

def test_parse_vendor():
    vendor = P.parse_vendor(fixture("vendor_salesforce.html"))
    assert vendor["slug"] == "salesforce" and vendor["name"] == "Salesforce"
    assert vendor["company_size"] == "10,001+ employees" and vendor["company_type"] == "public"
    assert vendor["founded"] == "1999" and vendor["stock_symbol"] == "CRM"
    assert vendor["headquarters"] == "One Market, Suite 300, San Francisco, CA 94105, United States"
    assert vendor["products_count"] == 37 and len(vendor["products"]) == 37
    assert vendor["products"][0]["slug"] == "salesforce-identity" and vendor["products"][0]["rating"]["tr_score"] == 7
    assert vendor["is_trustradius_customer"] is False
    dumped = json.dumps(vendor)
    for secret in ("apiKeyEncrypted", "primaryContact", "@salesforce.com", "emailDomains"):
        assert secret not in dumped
    hubspot = P.parse_vendor(fixture("vendor_hubspot.html"))
    assert hubspot["products_count"] == 12 and hubspot["is_trustradius_customer"] is True
    assert hubspot["keywords"][0] == "inbound marketing"
    assert P.parse_vendor(fixture("vendor_notfound.html")) is None
    assert P.parse_vendor(fixture("cloudflare_challenge.html")) is None


# ---- categories ------------------------------------------------------------------------------------

def test_parse_category_listing():
    page = P.parse_category(fixture("category_crm_p1.html"))
    cat = page["category"]
    assert cat["slug"] == "crm" and cat["acronym"] == "CRM" and cat["product_count"] == 173
    assert cat["name"] == "Customer Relationship Management (CRM)"
    assert cat["description"].startswith("CRM software centralizes")
    assert cat["overview"].startswith("What is CRM Software?")
    assert len(cat["faq"]) == 5 and cat["faq"][0]["question"] == "What is customer relationship management software?"
    assert cat["related_categories"][0] == {"name": "Contact Center", "slug": "contact-center",
                                            "link": "https://www.trustradius.com/categories/contact-center"}
    assert cat["videos"][0]["service"] == "youtube"
    assert page["offset"] == 0 and page["size"] == 25 and page["total"] == 1505
    assert len(page["products"]) == 25
    first = page["products"][0]
    assert first["slug"] == "bigin-by-zoho-crm" and first["position"] == 1
    assert first["vendor"]["slug"] == "zoho" and first["rating"]["tr_score"] == 8.844
    assert first["ranking_score"] == pytest.approx(8.632275)
    assert first["has_free_trial"] is True and first["starting_price"]["amount"] == 9
    assert first["awards"][0]["type"] == "toprated"
    assert first["feature_ratings"][0]["score"] == 8.808 and len(first["pros"]) == 10
    page2 = P.parse_category(fixture("category_crm_f25.html"))
    assert page2["offset"] == 25 and page2["products"][0]["position"] == 26 and page2["products"][0]["slug"] == "bigcontacts"
    assert P.parse_category(fixture("category_notfound.html")) is None
    assert P.parse_category(fixture("cloudflare_challenge.html")) is None


def test_parse_categories_index():
    groups = P.parse_categories_index(fixture("categories_index.html"))
    assert len(groups) == 19 and sum(g["categories_count"] for g in groups) == 987
    assert groups[0]["name"] == "Featured Categories"
    dev = groups[1]
    assert dev["name"] == "Development" and dev["categories_count"] == 54
    assert dev["categories"][0] == {"id": "55bd39171c5cdf1d004cffbc", "name": ".NET Development", "slug": "net-development",
                                    "link": "https://www.trustradius.com/categories/net-development",
                                    "description": dev["categories"][0]["description"], "is_featured": False}
    assert P.parse_categories_index(fixture("category_notfound.html")) is None


# ---- compare -------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def compare():
    return P.parse_compare(fixture("compare_hubspot_vs_salesforce.html"))


def test_parse_compare_products(compare):
    assert compare["link"] == "https://www.trustradius.com/compare-products/hubspot-crm-vs-salesforce-agentforce-sales"
    assert [p["slug"] for p in compare["products"]] == ["hubspot-crm", "salesforce-agentforce-sales"]
    hubspot, salesforce = compare["products"]
    assert hubspot["rating"] == {"average": 8.4, "count": 5542}
    assert hubspot["overview"]["tr_score"] == 8.431 and salesforce["overview"]["tr_score"] == 8.816
    assert hubspot["overview"]["starting_price"] == {"amount": 0, "currency": "USD"}
    assert hubspot["overview"]["starting_price_terms"] == "Per Month [Unlimited Users]"
    assert hubspot["overview"]["most_used_by"] is None
    assert [e["name"] for e in hubspot["pricing"]["editions"]] == ["Free Forever", "CRM Bundle"]
    assert len(salesforce["pricing"]["editions"]) == 5
    assert hubspot["pricing"]["offerings"] == {"Free Trial": True, "Free/Freemium Version": True,
                                                "Premium Consulting/Integration Services": True}
    assert salesforce["pricing"]["offerings"]["Free/Freemium Version"] is False
    assert hubspot["pricing"]["pricing_link"] == "https://www.hubspot.com/pricing/suite"
    assert hubspot["key_insights"]["would_buy_again"] == {"yes": 1608, "no": 55, "no_answer": 0}
    assert len(hubspot["screenshots"]) >= 3 and hubspot["screenshots"][0]["link"].startswith("https://media.trustradius.com/")
    assert [s["id"] for s in compare["sections"]][:3] == ["overview", "pricing", "community-pulse"]
    assert compare["sections"][3]["state"] == "empty"


def test_parse_compare_sections(compare):
    assert [(f["group"], len(f["features"])) for f in compare["features"]][:2] == [("Sales Force Automation", 9), ("Customer Service & Support", 3)]
    group = compare["features"][0]
    assert group["group_scores"][0] == {"product_slug": "hubspot-crm", "score": 8, "ratings_count": 1718,
                                        "vs_category": "2%", "trend": "positive"}
    assert group["features"][0]["scores"][0] == {"product_slug": "hubspot-crm", "score": 8.9, "ratings_count": 1663, "is_winner": True}
    assert [a["segment"] for a in compare["best_alternatives"]] == ["Small Businesses", "Medium-sized Companies", "Enterprises"]
    assert compare["best_alternatives"][0]["products"][0]["slug"] == "salesflare"
    assert compare["user_ratings"][0]["slug"] == "likelihood-to-recommend"
    assert compare["user_ratings"][0]["scores"][0] == {"product_slug": "hubspot-crm", "score": 8.6, "ratings_count": 1773}
    assert compare["considered_both_products"][0]["reviewer"]["name"] == "RAM KISHORE"
    assert compare["considered_both_products"][0]["text"].startswith("HubSpot CRM seemed way simpler")
    testimonials = {t["slug"]: t for t in compare["testimonials"]}
    assert testimonials["things-done-well"]["quotes"][0]["pros"][0].startswith("With a unified workflow")
    assert testimonials["things-done-well"]["quotes"][0]["text"] is None
    assert testimonials["likelihood-to-recommend"]["quotes"][0]["reviewer"]["name"] == "Nicholas Wisel"
    assert testimonials["product-availability"]["quotes"][0] == {"product_slug": "hubspot-crm", "has_answer": False}
    assert all(t["quotes"] for t in compare["testimonials"])


def test_parse_compare_three_and_not_found():
    three = P.parse_compare(fixture("compare_three_products.html"))
    assert [p["slug"] for p in three["products"]] == ["hubspot-crm", "pipedrive", "zoho-crm"]
    assert [p["overview"]["tr_score"] for p in three["products"]] == [8.427, 8.625, 8.437]
    assert len(three["user_ratings"][0]["scores"]) == 3
    assert P.parse_compare(fixture("compare_notfound.html")) is None
    assert P.parse_compare(fixture("cloudflare_challenge.html")) is None


# ---- search --------------------------------------------------------------------------------------

def test_parse_search():
    products = P.parse_search(fixture("complete_product.json"))
    assert products[1] == {"id": "552826bca2f0781500fa6c87", "name": "HubSpot CRM", "slug": "hubspot-crm",
                           "type": "product", "link": "https://www.trustradius.com/products/hubspot-crm"}
    categories = P.parse_search(fixture("complete_category.json"), "category")
    assert categories[0]["link"] == "https://www.trustradius.com/categories/crm" and len(categories) == 61
    vendors = P.parse_search(fixture("complete_vendor.json"), "vendor")
    assert vendors == [{"id": "5061d92eec3bbf02000000cb", "name": "HubSpot", "slug": "hubspot", "type": "vendor",
                        "link": "https://www.trustradius.com/vendors/hubspot"}]
    assert P.parse_search(fixture("complete_nomatch.json")) == []
    assert P.parse_search(None) == []
