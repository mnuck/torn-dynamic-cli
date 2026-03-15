---
id: torn-company-status
name: Torn Company Status Report
description: Daily company health check showing star rating risk, rank among peers, and income analysis
source: learned
triggers:
  - company status
  - torn company
  - torn chores
  - company report
  - how is my company
  - star rating
  - company check
  - candle shop
quality: high
---

# Torn Company Status Report

## The Insight

Star rating changes only happen on **Sundays**. The sole metric that determines rating is **weekly income** relative to other companies of the same type. Rating isn't a fixed income threshold — it's positional. A fixed-ish number of companies hold each star tier, so your risk depends on where you rank among peers and who's pushing from below.

## Why This Matters

Without this context, you might think your company is safe at 10★ just because income looks good. But if 30 nine-star companies are earning more than you, you're about to star down on Sunday. Conversely, if you're solidly mid-pack, you can relax.

## Recognition Pattern

When the user mentions any of:
- Checking on their company
- Torn chores / daily routine
- Star rating concerns
- Company income or ranking

## The Approach

Execute these 3 API calls and produce the analysis report below. **The API key MUST come from the `TORN_API_KEY` environment variable.**

### Step 1: Fetch Company Profile & Details

```bash
# Get company profile (ID, name, type, rating)
curl -s "https://api.torn.com/company/?selections=profile&key=$TORN_API_KEY"
# Returns: { "company": { "ID": N, "company_type": N, "name": "...", "rating": N, ... } }

# Get company financials (daily/weekly income and customers)
curl -s "https://api.torn.com/company/?selections=&key=$TORN_API_KEY"
# Returns: { "company": { "daily_income": N, "daily_customers": N, "weekly_income": N, "weekly_customers": N, ... } }
```

### Step 2: Fetch All Companies of Same Type

```bash
# Get all companies of the same type (e.g., type 8 = Candle Shop)
curl -s "https://api.torn.com/company/{company_type}?selections=companies&key=$TORN_API_KEY"
# Returns: { "company": { "id1": { "rating": N, "weekly_income": N }, ... } }
```

### Step 3: Analyze and Report

Using python3 (available on all systems), process the data:

```python
import json, sys
from datetime import datetime

# Parse the three API responses (profile, details, company_list)
# These should be passed in from the curl calls above

# Key calculations:
my_rating = profile['rating']
my_weekly = details['weekly_income']
my_daily = details['daily_income']

# Filter companies at my rating tier
same_tier = [(cid, c) for cid, c in all_companies.items() if c['rating'] == my_rating]
same_tier.sort(key=lambda x: x[1]['weekly_income'], reverse=True)

# My rank within tier
my_rank = len([c for c in same_tier if c[1]['weekly_income'] > my_weekly]) + 1
total_in_tier = len(same_tier)
below_me = total_in_tier - my_rank

# Floor of my tier
lowest_in_tier = min(c[1]['weekly_income'] for c in same_tier)
my_margin = my_weekly - lowest_in_tier

# Pressure from below (tier - 1)
lower_tier = [(cid, c) for cid, c in all_companies.items() if c['rating'] == my_rating - 1]
threatening = [c for c in lower_tier if c[1]['weekly_income'] > lowest_in_tier]
highest_lower = max((c[1]['weekly_income'] for c in lower_tier), default=0)

# Risk assessment
pct_below = (below_me / total_in_tier * 100) if total_in_tier > 0 else 0
if pct_below > 20:
    risk = "LOW"
elif pct_below >= 5 and len(threatening) == 0:
    risk = "MEDIUM"
elif pct_below < 5 or any(c[1]['weekly_income'] > my_weekly for c in lower_tier):
    risk = "HIGH"
else:
    risk = "MEDIUM"

# Sunday check
is_sunday = datetime.now().strftime('%A') == 'Sunday'
```

### Report Format

Present results in this format:

```
═══ Torn Company Status ═══
Company: {name} ({rating}★)
Weekly Income: ${weekly_income:,} | Daily: ${daily_income:,}
Daily Customers: {daily_customers:,} | Weekly: {weekly_customers:,}

── Your Position ({rating}★ tier) ──
Rank: #{my_rank} / {total_in_tier}
Shops below you: {below_me}
Lowest {rating}★ income: ${lowest_in_tier:,}
Your margin above floor: ${my_margin:,}

── Pressure from Below ({rating-1}★) ──
{rating-1}★ shops earning more than lowest {rating}★: {len(threatening)}
Highest {rating-1}★ income: ${highest_lower:,}

── Risk Assessment ──
{risk_emoji} {risk} risk of starring down

{if is_sunday: "⚠️  Rating changes happen TODAY!"}
{if not is_sunday: "Next rating change: Sunday"}
```

Where risk_emoji is:
- LOW = `\u2705`
- MEDIUM = `\u26a0\ufe0f`
- HIGH = `\ud83d\udea8`

## Gotchas

- **API v1 only**: The company list endpoint (`/company/{type}?selections=companies`) is only available in Torn API v1, not v2.
- **Rate limiting**: Torn API allows 100 calls/minute. These 3 calls are well within limits.
- **Weekly income resets**: Weekly income accumulates through the week. Early-week values will be low — don't panic on Monday.
- **Company type IDs**: Candle Shop = 8. If the user switches companies, the type_id comes from the profile call.
- **The "selections=" trick**: Passing empty selections to `/company/` returns the full default response including daily/weekly income and customers.
