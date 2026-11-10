# 🏆 TrustRadius Scraper

TrustRadius Scraper is a **free and open-source** scraper that gets you **unlimited** detailed TrustRadius data for free.

## ✨ What Can I Get?

- 🏆 **Full profiles of 32,000+ software products** — TrustRadius score, ratings, awards, feature scores, pricing & competitors
- 💬 **Every verified review, plus AI insights** — pros, cons, use cases, ROI & the reviewer's role, company size and industry
- ⚖️ **Side-by-side comparisons & alternatives** — feature-by-feature scores, pricing editions & the best picks by company size
- 🗂️ **All 987 software categories, ranked** — every product with its score, starting price & awards, plus full vendor profiles

## 🎥 Example: A Full TrustRadius Product Profile

```json
{
  "id": "55a57ad22be93031005d0aca",
  "name": "Slack",
  "slug": "slack",
  "link": "https://www.trustradius.com/products/slack",
  "vendor": { "name": "Salesforce", "slug": "salesforce", "link": "https://www.trustradius.com/vendors/salesforce" },
  "primary_category": { "name": "Collaboration", "slug": "collaboration" },
  "rating": {
    "average": 9,
    "count": 10288,
    "tr_score": 9.039,
    "written_reviews": { "average": 9.1, "count": 642, "tr_score": 9.066 },
    "quick_ratings": { "average": 9, "count": 9646, "tr_score": 9.033 }
  },
  "awards": [
    { "title": "Top Rated 2026", "type": "toprated", "state": "awarded", "expiration_date": "2027-06-11" }
  ],
  "feature_ratings": [
    { "name": "Chat", "score": 9.6, "ratings_count": 637, "category_average": 9 },
    { "name": "Mobile Access", "score": 9.4, "ratings_count": 603, "category_average": 8.6 }
  ],
  "competitors": [
    { "name": "Microsoft Teams", "slug": "microsoft-teams", "rating": { "average": 8.3, "count": 7834 } }
  ],
  "industry_install_share": {
    "total_installs": 37577,
    "industries": [
      { "name": "Professional, Scientific, and Technical Services", "company_count": 7736, "share_percent": 20.6 }
    ]
  },
  "pricing": {
    "starting_price": { "amount": 8.75, "currency": "USD", "period": "per month", "unit": "per user" },
    "has_free_version": true,
    "has_free_trial": true,
    "editions": [
      { "name": "Pro", "price": { "amount": 7.25, "currency": "USD" }, "period": "per month", "unit": "per user" },
      { "name": "Business+", "price": { "amount": 12.5, "currency": "USD" }, "period": "per month", "unit": "per user" }
    ]
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free TrustRadius Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/trustradius-scraper
cd trustradius-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=slack"
```

```json
{
  "id": "55a57ad22be93031005d0aca",
  "name": "Slack",
  "slug": "slack",
  "link": "https://www.trustradius.com/products/slack",
  "vendor": { "name": "Salesforce", "slug": "salesforce" },
  "primary_category": { "name": "Collaboration", "slug": "collaboration" },
  "rating": { "average": 9, "count": 10288, "tr_score": 9.039 },
  "awards": [{ "title": "Top Rated 2026", "state": "awarded" }],
  "feature_ratings": [{ "name": "Chat", "score": 9.6, "ratings_count": 638, "category_average": 9 }],
  "competitors": [
    { "name": "Microsoft Teams", "slug": "microsoft-teams", "rating": { "average": 8.3, "count": 7834 } },
    { "name": "Discord", "slug": "discord", "rating": { "average": 8.3, "count": 247 } }
  ],
  "pricing": {
    "starting_price": { "amount": 8.75, "currency": "USD", "period": "per month", "unit": "per user" },
    "has_free_version": true,
    "has_free_trial": true
  }
}
```

All 10 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

10 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Everything about one product: score, awards, features, pricing, competitors |
| Search Products | `/products/search` | Find any product, vendor or category by name, up to 100 |
| Product Reviews | `/products/reviews` | Verified reviews, 10 per page; filter by stars, size, industry, role |
| Review Details | `/reviews/details` | One review in full: every answer, ROI, alternatives, reviewer profile |
| Review Insights | `/products/insights` | AI summary of all reviews: overview, pros, cons and topics |
| Product Alternatives | `/products/alternatives` | Competitors plus the best alternatives by company size |
| Compare Products | `/products/compare` | 2-3 products side by side, feature by feature |
| Vendor Details | `/vendors/details` | Company profile and every product it sells, with ratings |
| Category Products | `/categories/products` | Ranked products in any category, 25 per page |
| List Categories | `/categories/list` | All 987 software categories in one call |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-trustradius-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-trustradius-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-trustradius-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/reviews",
    params={"product": "slack", "sort": "rating_low", "company_size": "large"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about TrustRadius Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/trustradius-scraper-github-whatsapp)

[![Ask Us by Email about TrustRadius Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20TrustRadius%20Scraper%20API&body=I%20need%20help%20using%20the%20TrustRadius%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/trustradius-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/trustradius-scraper)
