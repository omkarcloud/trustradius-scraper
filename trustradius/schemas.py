"""Marshmallow request schemas for every /trustradius/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    product    a product slug ("hubspot-crm") OR any trustradius.com product link
    review     a review slug ("hubspot-crm-2026-09-04-09-36-22"), a 24-character
               review id, OR a trustradius.com review link
    category   a category slug ("crm") OR a trustradius.com category link
    vendor     a vendor slug ("salesforce") OR a trustradius.com vendor link
    products   2-3 product slugs / links separated by commas, OR a
               trustradius.com compare link

The filter vocabularies (sort, stars, company_size, industry, role,
updated_within, os) are the site's own (trustradius/refs.py, read from its
reviews / category pages and JS on 2026-11-07).
"""
from marshmallow import ValidationError

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, LimitField, PageField,
                           QueryField, RefField, StrippedString)
from trustradius import refs

# 10 reviews per page; the site paginates every review (177 pages for HubSpot
# CRM) and answers an empty page past the end.
MAX_REVIEWS_PAGE = 2000


def _max_length(n):
    """validate.Length(max=n) that tolerates the None StrippedString returns
    for an empty value (marshmallow runs validators on it; len(None) is a 500)."""
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class ReviewRefField(RefField):
    resolver = staticmethod(refs.resolve_review)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class VendorRefField(RefField):
    resolver = staticmethod(refs.resolve_vendor)


class ProductsRefField(RefField):
    resolver = staticmethod(refs.resolve_products)


class CountryAlpha3Field(StrippedString):
    """ISO 3166-1 alpha-3 code, upper-cased (USA, IND, GBR) — the reviewer
    country key the site's own facets use."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        value = value.upper()
        if not (len(value) == 3 and value.isalpha()):
            raise ValidationError("Must be a 3-letter ISO country code (USA, IND, GBR, ...).")
        return value


class ProductsSearchSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "product, vendor or category name to search for"})
    type = ChoiceField(list(refs.SEARCH_TYPES), load_default="product", metadata={
        "description": "what to search: product (default), vendor or category"})
    limit = LimitField(default=20, max_size=100, metadata={
        "description": "maximum results (1-100, default 20)"})


class ProductSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "product slug (hubspot-crm) or a trustradius.com product link"})


class ProductReviewsSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "product slug (hubspot-crm) or a trustradius.com product link"})
    page = PageField(max_page=MAX_REVIEWS_PAGE, metadata={"description": "page number, 10 reviews per page"})
    sort = ChoiceField(list(refs.SORTS), load_default="recent", metadata={
        "description": "recent (default), oldest, rating_high or rating_low"})
    stars = CommaListField(allowed=refs.STARS, max_items=5, metadata={
        "description": "star buckets to keep, comma-separated 1-5 (5 = 9-10 of 10, 4 = 7-8, 3 = 5-6, 2 = 3-4, 1 = 1-2)"})
    company_size = ChoiceField(refs.COMPANY_SIZES, metadata={
        "description": "reviewer company size: small (1-50 employees), medium (51-1,000) or large (1,001+)"})
    industry = ChoiceField(list(refs.INDUSTRIES), metadata={
        "description": "reviewer industry slug, e.g. finance-and-insurance, information, health-care (see the facets in a reviews response)"})
    role = ChoiceField(refs.ROLES, metadata={
        "description": "reviewer role: user, support, manager, decision_maker, consultant, implementer or reseller"})
    country = CountryAlpha3Field(metadata={"description": "reviewer country as a 3-letter ISO code (USA, IND, GBR)"})
    keyword = StrippedString(required=False, load_default=None, validate=_max_length(100), metadata={
        "description": "free-text filter on the review text"})
    updated_within = ChoiceField(refs.UPDATED_WITHIN, metadata={
        "description": "only reviews published or updated within: month, 3months, 6months or year"})


class ReviewSchema(BaseSchema):
    review = ReviewRefField(metadata={
        "description": "review slug (hubspot-crm-2026-09-04-09-36-22), 24-character review id, or a trustradius.com review link"})


class ProductAlternativesSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "product slug (hubspot-crm) or a trustradius.com product link"})
    segment = ChoiceField(list(refs.ALTERNATIVE_SEGMENTS), load_default="all", metadata={
        "description": "best alternatives by reviewer company size: all (default), small, medium or large"})


class ProductsCompareSchema(BaseSchema):
    products = ProductsRefField(metadata={
        "description": "2-3 product slugs or links separated by commas (hubspot-crm,salesforce-agentforce-sales), or a trustradius.com compare link"})


class CategoryProductsSchema(BaseSchema):
    category = CategoryRefField(metadata={
        "description": "category slug (crm) or a trustradius.com category link"})
    page = PageField(max_page=refs.CATEGORY_MAX_PAGE, metadata={
        "description": "page number, 25 products per page (the site stops at page 40)"})
    free = Flag(metadata={"description": "true = only products with a free option (a free version or a free trial)"})
    top_rated = Flag(metadata={"description": "true = only products with a current Top Rated award"})
    os = ChoiceField(list(refs.OPERATING_SYSTEMS), metadata={
        "description": "only products that support this desktop OS: windows, mac or linux"})


class CategoriesListSchema(BaseSchema):
    """No parameters: the whole category tree."""


class VendorSchema(BaseSchema):
    vendor = VendorRefField(metadata={
        "description": "vendor slug (salesforce) or a trustradius.com vendor link"})
