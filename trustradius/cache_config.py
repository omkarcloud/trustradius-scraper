"""Cache TTL per /trustradius/* endpoint (cache.py, keyed on the validated
params). Review-site data moves slowly: a product's score shifts by a few
hundredths when a review lands, and the catalogue pages change with the
weekly publishing cadence. products/details and the pricing slice are two
cached page parses (api.py), so a client reading both pays two fetches once.
"""
from datetime import timedelta

# The product page parse (ratings, awards, features, FAQs, 5 featured reviews).
PRODUCT_CACHE = timedelta(days=7)
# The pricing page parse (editions, quotes, pricing alternatives) — vendors edit it rarely.
PRICING_CACHE = timedelta(days=7)
# A filtered reviews page: new reviews land daily on the big products.
REVIEWS_CACHE = timedelta(hours=24)
# A published review is immutable except for rare edits.
REVIEW_CACHE = timedelta(days=30)
# The competitors / segment-alternatives page is recomputed by the site monthly ("trustmap").
ALTERNATIVES_CACHE = timedelta(days=7)
# The AI synthesis page carries its own "last published" stamp, refreshed about monthly.
INSIGHTS_CACHE = timedelta(days=7)
# Compare pages are built from the same slowly moving product data.
COMPARE_CACHE = timedelta(days=7)
# A category listing reorders as ratings move.
CATEGORY_CACHE = timedelta(days=3)
# The category tree (972 categories) gains a handful of entries a month.
CATEGORIES_LIST_CACHE = timedelta(days=30)
# Vendor profile + product list.
VENDOR_CACHE = timedelta(days=7)
# Name autocomplete.
SEARCH_CACHE = timedelta(days=3)
# vendor name -> slug lookup used to link a product to its vendor page.
VENDOR_LOOKUP_CACHE = timedelta(days=30)
