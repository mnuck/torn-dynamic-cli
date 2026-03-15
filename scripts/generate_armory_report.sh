#!/bin/bash

# Armory Check Report Generator
# Generates report with costs and market links, accounting for loaned items

cd /Users/matthewnuckolls/torn_api/torn-dynamic-cli

# Item ID mapping
BOOTS_ID=653
GLOVES_ID=654
HELMET_ID=651
PANTS_ID=652
VEST_ID=332
LIQUID_ID=333
FLEXIBLE_ID=334

TARGET=3

echo "Fetching armor inventory..."
ARMOR=$(./torn faction --selections armor 2>/dev/null)

echo "Fetching item prices..."
PRICES=$(./torn torn items --ids "651,652,653,654,332,333,334" 2>/dev/null)

# Extract armor quantities and loaned counts by name
BOOTS_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Boots") | .quantity' 2>/dev/null || echo 0)
BOOTS_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Boots") | .loaned' 2>/dev/null || echo 0)
BOOTS=$((BOOTS_QTY - BOOTS_LOANED))

GLOVES_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Gloves") | .quantity' 2>/dev/null || echo 0)
GLOVES_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Gloves") | .loaned' 2>/dev/null || echo 0)
GLOVES=$((GLOVES_QTY - GLOVES_LOANED))

HELMET_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Helmet") | .quantity' 2>/dev/null || echo 0)
HELMET_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Helmet") | .loaned' 2>/dev/null || echo 0)
HELMET=$((HELMET_QTY - HELMET_LOANED))

PANTS_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Pants") | .quantity' 2>/dev/null || echo 0)
PANTS_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Pants") | .loaned' 2>/dev/null || echo 0)
PANTS=$((PANTS_QTY - PANTS_LOANED))

VEST_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Vest") | .quantity' 2>/dev/null || echo 0)
VEST_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Combat Vest") | .loaned' 2>/dev/null || echo 0)
VEST=$((VEST_QTY - VEST_LOANED))

LIQUID_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Liquid Body Armor") | .quantity' 2>/dev/null || echo 0)
LIQUID_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Liquid Body Armor") | .loaned' 2>/dev/null || echo 0)
LIQUID=$((LIQUID_QTY - LIQUID_LOANED))

FLEXIBLE_QTY=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Flexible Body Armor") | .quantity' 2>/dev/null || echo 0)
FLEXIBLE_LOANED=$(echo "$ARMOR" | jq '.armor[] | select(.name == "Flexible Body Armor") | .loaned' 2>/dev/null || echo 0)
FLEXIBLE=$((FLEXIBLE_QTY - FLEXIBLE_LOANED))

# Extract prices (using market_price)
BOOTS_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $BOOTS_ID) | .value.market_price" 2>/dev/null || echo 0)
GLOVES_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $GLOVES_ID) | .value.market_price" 2>/dev/null || echo 0)
HELMET_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $HELMET_ID) | .value.market_price" 2>/dev/null || echo 0)
PANTS_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $PANTS_ID) | .value.market_price" 2>/dev/null || echo 0)
VEST_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $VEST_ID) | .value.market_price" 2>/dev/null || echo 0)
LIQUID_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $LIQUID_ID) | .value.market_price" 2>/dev/null || echo 0)
FLEXIBLE_PRICE=$(echo "$PRICES" | jq ".items[] | select(.id == $FLEXIBLE_ID) | .value.market_price" 2>/dev/null || echo 0)

# Calculate needs (based on available, not total)
BOOTS_NEED=$((TARGET - BOOTS > 0 ? TARGET - BOOTS : 0))
GLOVES_NEED=$((TARGET - GLOVES > 0 ? TARGET - GLOVES : 0))
HELMET_NEED=$((TARGET - HELMET > 0 ? TARGET - HELMET : 0))
PANTS_NEED=$((TARGET - PANTS > 0 ? TARGET - PANTS : 0))
VEST_NEED=$((TARGET - VEST > 0 ? TARGET - VEST : 0))
LIQUID_NEED=$((TARGET - LIQUID > 0 ? TARGET - LIQUID : 0))
FLEXIBLE_NEED=$((TARGET - FLEXIBLE > 0 ? TARGET - FLEXIBLE : 0))

# Calculate costs
BOOTS_COST=$((BOOTS_NEED * BOOTS_PRICE))
GLOVES_COST=$((GLOVES_NEED * GLOVES_PRICE))
HELMET_COST=$((HELMET_NEED * HELMET_PRICE))
PANTS_COST=$((PANTS_NEED * PANTS_PRICE))
VEST_COST=$((VEST_NEED * VEST_PRICE))
LIQUID_COST=$((LIQUID_NEED * LIQUID_PRICE))
FLEXIBLE_COST=$((FLEXIBLE_NEED * FLEXIBLE_PRICE))

TOTAL_UNITS=$((BOOTS_NEED + GLOVES_NEED + HELMET_NEED + PANTS_NEED + VEST_NEED + LIQUID_NEED + FLEXIBLE_NEED))
TOTAL_COST=$((BOOTS_COST + GLOVES_COST + HELMET_COST + PANTS_COST + VEST_COST + LIQUID_COST + FLEXIBLE_COST))

# Format numbers with commas
format_number() {
    echo "$1" | awk '{printf "%'"'"'d\n", $0}'
}

# Generate report
cat > armory-report.md << REPORT
## Armory Check Report
Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

### Combat Armor

| Item | Available | Loaned | Need | Unit Cost | Total Cost | Market Link |
|------|-----------|--------|------|-----------|------------|-------------|
| [Combat Boots](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=653&sortField=price&sortOrder=ASC) | $BOOTS | $BOOTS_LOANED | $BOOTS_NEED | \$$(format_number $BOOTS_PRICE) | \$$(format_number $BOOTS_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=653&sortField=price&sortOrder=ASC) |
| [Combat Gloves](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=654&sortField=price&sortOrder=ASC) | $GLOVES | $GLOVES_LOANED | $GLOVES_NEED | \$$(format_number $GLOVES_PRICE) | \$$(format_number $GLOVES_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=654&sortField=price&sortOrder=ASC) |
| [Combat Helmet](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=651&sortField=price&sortOrder=ASC) | $HELMET | $HELMET_LOANED | $HELMET_NEED | \$$(format_number $HELMET_PRICE) | \$$(format_number $HELMET_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=651&sortField=price&sortOrder=ASC) |
| [Combat Pants](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=652&sortField=price&sortOrder=ASC) | $PANTS | $PANTS_LOANED | $PANTS_NEED | \$$(format_number $PANTS_PRICE) | \$$(format_number $PANTS_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=652&sortField=price&sortOrder=ASC) |
| [Combat Vest](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=332&sortField=price&sortOrder=ASC) | $VEST | $VEST_LOANED | $VEST_NEED | \$$(format_number $VEST_PRICE) | \$$(format_number $VEST_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=332&sortField=price&sortOrder=ASC) |

### Advanced Armor

| Item | Available | Loaned | Need | Unit Cost | Total Cost | Market Link |
|------|-----------|--------|------|-----------|------------|-------------|
| [Liquid Body Armor](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=333&sortField=price&sortOrder=ASC) | $LIQUID | $LIQUID_LOANED | $LIQUID_NEED | \$$(format_number $LIQUID_PRICE) | \$$(format_number $LIQUID_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=333&sortField=price&sortOrder=ASC) |
| [Flexible Body Armor](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=334&sortField=price&sortOrder=ASC) | $FLEXIBLE | $FLEXIBLE_LOANED | $FLEXIBLE_NEED | \$$(format_number $FLEXIBLE_PRICE) | \$$(format_number $FLEXIBLE_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=334&sortField=price&sortOrder=ASC) |

**Summary:**
- Total units to purchase: $TOTAL_UNITS
- **Total cost to restock: \$$(format_number $TOTAL_COST)**

> **Pull \$$(format_number $TOTAL_COST) from vault** to cover this restock.

---
_Target inventory: $TARGET units available per item_
_Updated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")_
REPORT

echo "✓ Report generated: armory-report.md"
echo ""
echo "=== Summary ==="
echo "Total units needed: $TOTAL_UNITS"
echo "Total cost: \$$(format_number $TOTAL_COST)"
