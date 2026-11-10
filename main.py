"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas the API uses, so defaults
are filled in and a slug or a trustradius.com link both work.
"""
import json
import os

from trustradius import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def run(schema_cls, fn, **params):
    return fn(**schema_cls().load(params))


if __name__ == "__main__":
    # a full software profile — TrustRadius score, awards, feature scores, pricing editions, pros and cons
    save("product_slack.json",
         run(schemas.ProductSchema, api.product_details, product="slack"))

    # verified reviews, 10 per page — filter by stars, company size, industry, role or country
    save("reviews_slack.json",
         run(schemas.ProductReviewsSchema, api.products_reviews, product="slack"))

    # two or three products side by side — scores, pricing, feature-by-feature ratings
    save("compare_slack_vs_teams.json",
         run(schemas.ProductsCompareSchema, api.products_compare, products="slack,microsoft-teams"))
