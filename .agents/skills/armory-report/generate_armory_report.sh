#!/bin/bash

# Armory Check Report Generator
# Generates report with costs and market links, accounting for loaned items
#
# Run from the repo root (the script shells out to ./torn). If TORN_REPO_ROOT
# is set we cd there; otherwise we cd to the repo root inferred from this
# script's own location (../../.. relative to .agents/skills/armory-report/).

if [ -n "$TORN_REPO_ROOT" ]; then
    cd "$TORN_REPO_ROOT"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR/../../.."
fi

# Item ID mapping - armor
BOOTS_ID=653
GLOVES_ID=654
HELMET_ID=651
PANTS_ID=652
VEST_ID=332
LIQUID_ID=333
FLEXIBLE_ID=334

# Item ID mapping - medical
EMPTY_BAG_ID=731
SFAK_ID=68
FAK_ID=67
IPECAC_ID=1363
BAG_APOS_ID=732
BAG_ANEG_ID=733
BAG_BPOS_ID=734
BAG_BNEG_ID=735
BAG_ABPOS_ID=736
BAG_ABNEG_ID=737
BAG_OPOS_ID=738
BAG_ONEG_ID=739

ARMOR_TARGET=3
EMPTY_BAG_TARGET=300
SFAK_TARGET=500
FAK_TARGET=200
IPECAC_TARGET=100
BLOOD_TARGET=300

echo "Fetching armor inventory..."
ARMOR=$(./torn faction --selections armor 2>/dev/null)

echo "Fetching medical inventory..."
MEDICAL=$(./torn faction --selections medical 2>/dev/null)

echo "Fetching item prices..."
PRICES=$(./torn torn items --ids "651,652,653,654,332,333,334,731,68,67,1363,732,733,734,735,736,737,738,739" 2>/dev/null)

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

# Extract medical quantities (no loaned for medical items)
med_qty() { result=$(echo "$MEDICAL" | jq --arg n "$1" '.medical[] | select(.name == $n) | .quantity' 2>/dev/null); echo "${result:-0}"; }

EMPTY_BAG=$(med_qty "Empty Blood Bag")
SFAK=$(med_qty "Small First Aid Kit")
FAK=$(med_qty "First Aid Kit")
IPECAC=$(med_qty "Ipecac Syrup")
BAG_APOS=$(med_qty "Blood Bag : A+")
BAG_ANEG=$(med_qty "Blood Bag : A-")
BAG_BPOS=$(med_qty "Blood Bag : B+")
BAG_BNEG=$(med_qty "Blood Bag : B-")
BAG_ABPOS=$(med_qty "Blood Bag : AB+")
BAG_ABNEG=$(med_qty "Blood Bag : AB-")
BAG_OPOS=$(med_qty "Blood Bag : O+")
BAG_ONEG=$(med_qty "Blood Bag : O-")

# Extract prices (using market_price)
price_of() { echo "$PRICES" | jq ".items[] | select(.id == $1) | .value.market_price" 2>/dev/null || echo 0; }

BOOTS_PRICE=$(price_of $BOOTS_ID)
GLOVES_PRICE=$(price_of $GLOVES_ID)
HELMET_PRICE=$(price_of $HELMET_ID)
PANTS_PRICE=$(price_of $PANTS_ID)
VEST_PRICE=$(price_of $VEST_ID)
LIQUID_PRICE=$(price_of $LIQUID_ID)
FLEXIBLE_PRICE=$(price_of $FLEXIBLE_ID)

EMPTY_BAG_PRICE=$(price_of $EMPTY_BAG_ID)
SFAK_PRICE=$(price_of $SFAK_ID)
FAK_PRICE=$(price_of $FAK_ID)
IPECAC_PRICE=$(price_of $IPECAC_ID)
BAG_APOS_PRICE=$(price_of $BAG_APOS_ID)
BAG_ANEG_PRICE=$(price_of $BAG_ANEG_ID)
BAG_BPOS_PRICE=$(price_of $BAG_BPOS_ID)
BAG_BNEG_PRICE=$(price_of $BAG_BNEG_ID)
BAG_ABPOS_PRICE=$(price_of $BAG_ABPOS_ID)
BAG_ABNEG_PRICE=$(price_of $BAG_ABNEG_ID)
BAG_OPOS_PRICE=$(price_of $BAG_OPOS_ID)
BAG_ONEG_PRICE=$(price_of $BAG_ONEG_ID)

# Calculate needs
need() { echo $(($2 - $1 > 0 ? $2 - $1 : 0)); }

BOOTS_NEED=$(need $BOOTS $ARMOR_TARGET)
GLOVES_NEED=$(need $GLOVES $ARMOR_TARGET)
HELMET_NEED=$(need $HELMET $ARMOR_TARGET)
PANTS_NEED=$(need $PANTS $ARMOR_TARGET)
VEST_NEED=$(need $VEST $ARMOR_TARGET)
LIQUID_NEED=$(need $LIQUID $ARMOR_TARGET)
FLEXIBLE_NEED=$(need $FLEXIBLE $ARMOR_TARGET)

EMPTY_BAG_NEED=$(need $EMPTY_BAG $EMPTY_BAG_TARGET)
SFAK_NEED=$(need $SFAK $SFAK_TARGET)
FAK_NEED=$(need $FAK $FAK_TARGET)
IPECAC_NEED=$(need $IPECAC $IPECAC_TARGET)
BAG_APOS_NEED=$(need $BAG_APOS $BLOOD_TARGET)
BAG_ANEG_NEED=$(need $BAG_ANEG $BLOOD_TARGET)
BAG_BPOS_NEED=$(need $BAG_BPOS $BLOOD_TARGET)
BAG_BNEG_NEED=$(need $BAG_BNEG $BLOOD_TARGET)
BAG_ABPOS_NEED=$(need $BAG_ABPOS $BLOOD_TARGET)
BAG_ABNEG_NEED=$(need $BAG_ABNEG $BLOOD_TARGET)
BAG_OPOS_NEED=$(need $BAG_OPOS $BLOOD_TARGET)
BAG_ONEG_NEED=$(need $BAG_ONEG $BLOOD_TARGET)

# Calculate costs
BOOTS_COST=$((BOOTS_NEED * BOOTS_PRICE))
GLOVES_COST=$((GLOVES_NEED * GLOVES_PRICE))
HELMET_COST=$((HELMET_NEED * HELMET_PRICE))
PANTS_COST=$((PANTS_NEED * PANTS_PRICE))
VEST_COST=$((VEST_NEED * VEST_PRICE))
LIQUID_COST=$((LIQUID_NEED * LIQUID_PRICE))
FLEXIBLE_COST=$((FLEXIBLE_NEED * FLEXIBLE_PRICE))

EMPTY_BAG_COST=$((EMPTY_BAG_NEED * EMPTY_BAG_PRICE))
SFAK_COST=$((SFAK_NEED * SFAK_PRICE))
FAK_COST=$((FAK_NEED * FAK_PRICE))
IPECAC_COST=$((IPECAC_NEED * IPECAC_PRICE))
BAG_APOS_COST=$((BAG_APOS_NEED * BAG_APOS_PRICE))
BAG_ANEG_COST=$((BAG_ANEG_NEED * BAG_ANEG_PRICE))
BAG_BPOS_COST=$((BAG_BPOS_NEED * BAG_BPOS_PRICE))
BAG_BNEG_COST=$((BAG_BNEG_NEED * BAG_BNEG_PRICE))
BAG_ABPOS_COST=$((BAG_ABPOS_NEED * BAG_ABPOS_PRICE))
BAG_ABNEG_COST=$((BAG_ABNEG_NEED * BAG_ABNEG_PRICE))
BAG_OPOS_COST=$((BAG_OPOS_NEED * BAG_OPOS_PRICE))
BAG_ONEG_COST=$((BAG_ONEG_NEED * BAG_ONEG_PRICE))

ARMOR_UNITS=$((BOOTS_NEED + GLOVES_NEED + HELMET_NEED + PANTS_NEED + VEST_NEED + LIQUID_NEED + FLEXIBLE_NEED))
ARMOR_COST=$((BOOTS_COST + GLOVES_COST + HELMET_COST + PANTS_COST + VEST_COST + LIQUID_COST + FLEXIBLE_COST))

MEDICAL_UNITS=$((EMPTY_BAG_NEED + SFAK_NEED + FAK_NEED + IPECAC_NEED + BAG_APOS_NEED + BAG_ANEG_NEED + BAG_BPOS_NEED + BAG_BNEG_NEED + BAG_ABPOS_NEED + BAG_ABNEG_NEED + BAG_OPOS_NEED + BAG_ONEG_NEED))
MEDICAL_COST=$((EMPTY_BAG_COST + SFAK_COST + FAK_COST + IPECAC_COST + BAG_APOS_COST + BAG_ANEG_COST + BAG_BPOS_COST + BAG_BNEG_COST + BAG_ABPOS_COST + BAG_ABNEG_COST + BAG_OPOS_COST + BAG_ONEG_COST))

TOTAL_UNITS=$((ARMOR_UNITS + MEDICAL_UNITS))
TOTAL_COST=$((ARMOR_COST + MEDICAL_COST))

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

### Medical Supplies

| Item | Available | Need | Unit Cost | Total Cost | Market Link |
|------|-----------|------|-----------|------------|-------------|
| [Empty Blood Bag](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=731&sortField=price&sortOrder=ASC) | $EMPTY_BAG | $EMPTY_BAG_NEED | \$$(format_number $EMPTY_BAG_PRICE) | \$$(format_number $EMPTY_BAG_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=731&sortField=price&sortOrder=ASC) |
| [Small First Aid Kit](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=68&sortField=price&sortOrder=ASC) | $SFAK | $SFAK_NEED | \$$(format_number $SFAK_PRICE) | \$$(format_number $SFAK_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=68&sortField=price&sortOrder=ASC) |
| [First Aid Kit](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=67&sortField=price&sortOrder=ASC) | $FAK | $FAK_NEED | \$$(format_number $FAK_PRICE) | \$$(format_number $FAK_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=67&sortField=price&sortOrder=ASC) |
| [Ipecac Syrup](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=1363&sortField=price&sortOrder=ASC) | $IPECAC | $IPECAC_NEED | \$$(format_number $IPECAC_PRICE) | \$$(format_number $IPECAC_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=1363&sortField=price&sortOrder=ASC) |
| [Blood Bag : A+](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=732&sortField=price&sortOrder=ASC) | $BAG_APOS | $BAG_APOS_NEED | \$$(format_number $BAG_APOS_PRICE) | \$$(format_number $BAG_APOS_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=732&sortField=price&sortOrder=ASC) |
| [Blood Bag : A-](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=733&sortField=price&sortOrder=ASC) | $BAG_ANEG | $BAG_ANEG_NEED | \$$(format_number $BAG_ANEG_PRICE) | \$$(format_number $BAG_ANEG_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=733&sortField=price&sortOrder=ASC) |
| [Blood Bag : B+](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=734&sortField=price&sortOrder=ASC) | $BAG_BPOS | $BAG_BPOS_NEED | \$$(format_number $BAG_BPOS_PRICE) | \$$(format_number $BAG_BPOS_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=734&sortField=price&sortOrder=ASC) |
| [Blood Bag : B-](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=735&sortField=price&sortOrder=ASC) | $BAG_BNEG | $BAG_BNEG_NEED | \$$(format_number $BAG_BNEG_PRICE) | \$$(format_number $BAG_BNEG_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=735&sortField=price&sortOrder=ASC) |
| [Blood Bag : AB+](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=736&sortField=price&sortOrder=ASC) | $BAG_ABPOS | $BAG_ABPOS_NEED | \$$(format_number $BAG_ABPOS_PRICE) | \$$(format_number $BAG_ABPOS_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=736&sortField=price&sortOrder=ASC) |
| [Blood Bag : AB-](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=737&sortField=price&sortOrder=ASC) | $BAG_ABNEG | $BAG_ABNEG_NEED | \$$(format_number $BAG_ABNEG_PRICE) | \$$(format_number $BAG_ABNEG_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=737&sortField=price&sortOrder=ASC) |
| [Blood Bag : O+](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=738&sortField=price&sortOrder=ASC) | $BAG_OPOS | $BAG_OPOS_NEED | \$$(format_number $BAG_OPOS_PRICE) | \$$(format_number $BAG_OPOS_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=738&sortField=price&sortOrder=ASC) |
| [Blood Bag : O-](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=739&sortField=price&sortOrder=ASC) | $BAG_ONEG | $BAG_ONEG_NEED | \$$(format_number $BAG_ONEG_PRICE) | \$$(format_number $BAG_ONEG_COST) | [↗](https://www.torn.com/page.php?sid=ItemMarket#/market/view=search&itemID=739&sortField=price&sortOrder=ASC) |

**Summary:**
- Total units to purchase: $(format_number $TOTAL_UNITS)
- **Total cost to restock: \$$(format_number $TOTAL_COST)**

> **Pull \$$(format_number $TOTAL_COST) from vault** to cover this restock.

---
_Armor target: $ARMOR_TARGET units available per item_
_Medical targets: Empty Blood Bag x$EMPTY_BAG_TARGET, Small FAK x$SFAK_TARGET, FAK x$FAK_TARGET, Ipecac x$IPECAC_TARGET, Blood bags x$BLOOD_TARGET each_
_Updated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")_
REPORT

echo "✓ Report generated: armory-report.md"
echo ""
echo "=== Summary ==="
echo "Total units needed: $TOTAL_UNITS"
echo "Total cost: \$$(format_number $TOTAL_COST)"
