"""Offline tests for the /trustradius/* request schemas and reference resolvers.

    python -m pytest trustradius/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trustradius import refs, schemas  # noqa: E402


# ---- resolvers ------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("hubspot-crm", "hubspot-crm"),
    ("  HubSpot-CRM ", "hubspot-crm"),
    ("https://www.trustradius.com/products/hubspot-crm", "hubspot-crm"),
    ("https://www.trustradius.com/products/hubspot-crm/reviews?page=2", "hubspot-crm"),
    ("https://trustradius.com/products/salesforce-agentforce-sales/pricing", "salesforce-agentforce-sales"),
    ("//www.trustradius.com/products/korero/competitors", "korero"),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", [
    "", "hub spot", "https://example.com/products/hubspot-crm",
    "https://www.trustradius.com/vendors/hubspot", "https://www.trustradius.com/",
])
def test_resolve_product_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


@pytest.mark.parametrize("value,expected", [
    ("hubspot-crm-2026-09-04-09-36-22", "hubspot-crm-2026-09-04-09-36-22"),
    ("hubspot-crm-2026-10-15-05-55-40-332", "hubspot-crm-2026-10-15-05-55-40-332"),
    ("68f8ed57b7f428e941c79c28", "68f8ed57b7f428e941c79c28"),
    ("https://www.trustradius.com/reviews/salesforce-sales-cloud-2025-10-22-09-42-29#comments",
     "salesforce-sales-cloud-2025-10-22-09-42-29"),
])
def test_resolve_review(value, expected):
    assert refs.resolve_review(value) == expected


@pytest.mark.parametrize("value", ["", "hubspot-crm", "https://www.trustradius.com/products/hubspot-crm",
                                   "https://example.com/reviews/hubspot-crm-2026-09-04-09-36-22"])
def test_resolve_review_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_review(value)


@pytest.mark.parametrize("value,expected", [
    ("crm", "crm"),
    ("https://www.trustradius.com/categories/crm", "crm"),
    ("https://www.trustradius.com/crm", "crm"),          # the autocomplete's own category path
    ("https://www.trustradius.com/categories/net-development?f=25", "net-development"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


def test_resolve_category_invalid():
    with pytest.raises(ValueError):
        refs.resolve_category("https://www.trustradius.com/products/hubspot-crm")
    with pytest.raises(ValueError):
        refs.resolve_category("")


@pytest.mark.parametrize("value,expected", [
    ("salesforce", "salesforce"),
    ("https://www.trustradius.com/vendors/hubspot", "hubspot"),
])
def test_resolve_vendor(value, expected):
    assert refs.resolve_vendor(value) == expected


def test_resolve_vendor_invalid():
    with pytest.raises(ValueError):
        refs.resolve_vendor("https://www.trustradius.com/products/hubspot-crm")


def test_resolve_products_sorts_and_dedupes():
    assert refs.resolve_products("salesforce-agentforce-sales, hubspot-crm,hubspot-crm") == \
        ["hubspot-crm", "salesforce-agentforce-sales"]
    assert refs.resolve_products("https://www.trustradius.com/compare-products/hubspot-crm-vs-pipedrive-vs-zoho-crm") == \
        ["hubspot-crm", "pipedrive", "zoho-crm"]
    assert refs.resolve_products("https://www.trustradius.com/products/zoho-crm,hubspot-crm") == ["hubspot-crm", "zoho-crm"]


@pytest.mark.parametrize("value", ["hubspot-crm", "hubspot-crm,hubspot-crm", "a,b,c,d", "", "https://example.com/compare-products/a-vs-b"])
def test_resolve_products_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_products(value)


def test_industry_table():
    assert len(refs.INDUSTRIES) == 20
    assert refs.industry_for_tr_code("4") == {"slug": "information", "name": "Information"}
    assert refs.industry_for_tr_code("96")["slug"] == "professional-services"
    assert refs.industry_for_tr_code("9999") is None
    assert refs.INDUSTRY_BY_NAICS["52"] == "finance-and-insurance"


def test_links():
    assert refs.product_link("hubspot-crm") == "https://www.trustradius.com/products/hubspot-crm"
    assert refs.compare_link(["zoho-crm", "hubspot-crm"]) == "https://www.trustradius.com/compare-products/hubspot-crm-vs-zoho-crm"
    assert refs.absolute("/reviews/x") == "https://www.trustradius.com/reviews/x"
    assert refs.absolute("https://media.trustradius.com/a.png") == "https://media.trustradius.com/a.png"
    assert refs.absolute(None) is None


# ---- schemas --------------------------------------------------------------------------

def test_search_schema():
    assert schemas.ProductsSearchSchema().load({"query": " hubspot "}) == {"query": "hubspot", "type": "product", "limit": 20}
    assert schemas.ProductsSearchSchema().load({"query": "crm", "type": "Category", "limit": "5"})["type"] == "category"
    with pytest.raises(ValidationError):
        schemas.ProductsSearchSchema().load({})
    with pytest.raises(ValidationError):
        schemas.ProductsSearchSchema().load({"query": "x", "type": "user"})
    with pytest.raises(ValidationError):
        schemas.ProductsSearchSchema().load({"query": "x", "limit": "101"})


def test_product_schema_accepts_slug_and_link():
    assert schemas.ProductSchema().load({"product": "HubSpot-CRM"}) == {"product": "hubspot-crm"}
    assert schemas.ProductSchema().load({"product": "https://www.trustradius.com/products/hubspot-crm/reviews"}) == \
        {"product": "hubspot-crm"}


@pytest.mark.parametrize("value", ["", "https://example.com/products/x", "a b"])
def test_product_schema_rejects(value):
    with pytest.raises(ValidationError):
        schemas.ProductSchema().load({"product": value})


def test_product_schema_rejects_sibling_params():
    with pytest.raises(ValidationError) as e:
        schemas.ProductSchema().load({"product": "hubspot-crm", "url": "https://www.trustradius.com/products/hubspot-crm"})
    assert "url" in str(e.value)


def test_reviews_schema_defaults_and_filters():
    loaded = schemas.ProductReviewsSchema().load({"product": "hubspot-crm"})
    assert loaded == {"product": "hubspot-crm", "page": 1, "sort": "recent", "stars": None, "company_size": None,
                      "industry": None, "role": None, "country": None, "keyword": None, "updated_within": None}
    loaded = schemas.ProductReviewsSchema().load({
        "product": "hubspot-crm", "page": "3", "sort": "Rating_High", "stars": "5, 4,5", "company_size": "Small",
        "industry": "finance-and-insurance", "role": "decision_maker", "country": "usa", "keyword": " pipeline ",
        "updated_within": "3months"})
    assert loaded["page"] == 3 and loaded["sort"] == "rating_high"
    assert loaded["stars"] == ["5", "4"]
    assert loaded["company_size"] == "small"
    assert loaded["role"] == "decisionMaker"          # mapped to the site's token
    assert loaded["country"] == "USA"
    assert loaded["keyword"] == "pipeline"
    assert loaded["updated_within"] == "3months"
    assert schemas.ProductReviewsSchema().load({"product": "hubspot-crm", "keyword": " "})["keyword"] is None


@pytest.mark.parametrize("bad", [
    {"sort": "newest"}, {"stars": "6"}, {"company_size": "enterprise"}, {"industry": "banking"},
    {"role": "ceo"}, {"country": "US"}, {"updated_within": "week"}, {"page": "0"}, {"page": "2001"},
])
def test_reviews_schema_rejects(bad):
    with pytest.raises(ValidationError) as e:
        schemas.ProductReviewsSchema().load({"product": "hubspot-crm", **bad})
    assert list(bad)[0] in str(e.value)


def test_review_schema():
    assert schemas.ReviewSchema().load({"review": "hubspot-crm-2026-09-04-09-36-22"}) == {"review": "hubspot-crm-2026-09-04-09-36-22"}
    assert schemas.ReviewSchema().load({"review": "https://www.trustradius.com/reviews/korero-2021-04-14-07-40-44"})["review"] == \
        "korero-2021-04-14-07-40-44"
    with pytest.raises(ValidationError):
        schemas.ReviewSchema().load({"review": "hubspot-crm"})


def test_alternatives_schema():
    assert schemas.ProductAlternativesSchema().load({"product": "korero"}) == {"product": "korero", "segment": "all"}
    assert schemas.ProductAlternativesSchema().load({"product": "korero", "segment": "Large"})["segment"] == "large"
    with pytest.raises(ValidationError):
        schemas.ProductAlternativesSchema().load({"product": "korero", "segment": "enterprise"})


def test_compare_schema():
    loaded = schemas.ProductsCompareSchema().load({"products": "salesforce-agentforce-sales,hubspot-crm"})
    assert loaded == {"products": ["hubspot-crm", "salesforce-agentforce-sales"]}
    with pytest.raises(ValidationError) as e:
        schemas.ProductsCompareSchema().load({"products": "hubspot-crm"})
    assert "at least 2" in str(e.value)
    with pytest.raises(ValidationError):
        schemas.ProductsCompareSchema().load({"products": "a,b,c,d"})


def test_category_products_schema():
    loaded = schemas.CategoryProductsSchema().load({"category": "https://www.trustradius.com/categories/crm"})
    assert loaded == {"category": "crm", "page": 1, "free": None, "top_rated": None, "os": None}
    loaded = schemas.CategoryProductsSchema().load({"category": "crm", "page": "40", "free": "yes", "top_rated": "0", "os": "Mac"})
    assert loaded["page"] == 40 and loaded["free"] is True and loaded["top_rated"] is False and loaded["os"] == "mac"
    with pytest.raises(ValidationError) as e:
        schemas.CategoryProductsSchema().load({"category": "crm", "page": "41"})
    assert "page" in str(e.value)
    with pytest.raises(ValidationError):
        schemas.CategoryProductsSchema().load({"category": "crm", "os": "android"})
    with pytest.raises(ValidationError):
        schemas.CategoryProductsSchema().load({"category": "crm", "free": "maybe"})


def test_categories_list_schema_takes_nothing():
    assert schemas.CategoriesListSchema().load({}) == {}
    with pytest.raises(ValidationError):
        schemas.CategoriesListSchema().load({"page": "2"})


def test_vendor_schema():
    assert schemas.VendorSchema().load({"vendor": "https://www.trustradius.com/vendors/salesforce"}) == {"vendor": "salesforce"}
    with pytest.raises(ValidationError):
        schemas.VendorSchema().load({"vendor": ""})
