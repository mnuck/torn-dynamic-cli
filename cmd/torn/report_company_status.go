package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"time"

	"github.com/spf13/cobra"
)

// newCompanyStatusCmd creates the "company" subcommand under "report".
// It implements the Torn Company Status skill described in .agents/skills/torn-company-status/SKILL.md.
func newCompanyStatusCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "company",
		Short: "Show daily company health status",
		Long: `Provides a star‑rating risk assessment based on weekly income\nrelative to peer companies of the same type. Uses three API calls:\n  1. profile (rating, name, type)\n  2. details (daily/weekly income & customers)\n  3. list of companies of the same type`,
		RunE: func(cmd *cobra.Command, args []string) error {
			apiKey, err := getAPIKey(cmd)
			if err != nil {
				return err
			}
			return runCompanyStatus(apiKey)
		},
	}
	return cmd
}

// runCompanyStatus performs the three API requests and prints the formatted report.
func runCompanyStatus(apiKey string) error {
	// 1️⃣ Profile
	profilePages, err := fetchAllPages(apiKey, fmt.Sprintf("https://api.torn.com/company/?selections=profile&key=%s", apiKey))
	if err != nil {
		return fmt.Errorf("fetch profile: %w", err)
	}
	if len(profilePages) == 0 {
		return fmt.Errorf("empty profile response")
	}
	var profile map[string]interface{}
	if err := json.Unmarshal(profilePages[0], &profile); err != nil {
		return fmt.Errorf("failed to unmarshal profile: %w", err)
	}

	// 2️⃣ Details (empty selections)
	detailsPages, err := fetchAllPages(apiKey, fmt.Sprintf("https://api.torn.com/company/?selections=&key=%s", apiKey))
	if err != nil {
		return fmt.Errorf("fetch details: %w", err)
	}
	if len(detailsPages) == 0 {
		return fmt.Errorf("empty details response")
	}
	var details map[string]interface{}
	if err := json.Unmarshal(detailsPages[0], &details); err != nil {
		return fmt.Errorf("failed to unmarshal details: %w", err)
	}

	// 3️⃣ List of companies of the same type
	var companyType string
	if comp, ok := profile["company"].(map[string]interface{}); ok {
		if t, ok := comp["company_type"].(string); ok {
			companyType = t
		}
	}

	if companyType == "" {
		return fmt.Errorf("could not determine company type from profile")
	}

	listURL := fmt.Sprintf("https://api.torn.com/company/%s?selections=companies&key=%s", companyType, apiKey)
	listPages, err := fetchAllPages(apiKey, listURL)
	if err != nil {
		return fmt.Errorf("fetch list: %w", err)
	}
	if len(listPages) == 0 {
		return fmt.Errorf("empty list response")
	}
	var list map[string]interface{}
	if err := json.Unmarshal(listPages[0], &list); err != nil {
		return fmt.Errorf("failed to unmarshal list: %w", err)
	}

	// Generate report string
	report, err := generateCompanyReport(profile, details, list)
	if err != nil {
		return err
	}
	fmt.Print(report)
	return nil
}

// generateCompanyReport creates the formatted report string.
// It receives the parsed JSON objects for profile, details, and list.
func generateCompanyReport(profile, details, list map[string]interface{}) (string, error) {
	// Extract fields
	var myName string
	var myRating int
	if comp, ok := profile["company"].(map[string]interface{}); ok {
		myName, _ = comp["name"].(string)
		myRating = int(comp["rating"].(float64))
	}

	var myWeekly, myDaily, myDailyCustomers, myWeeklyCustomers int64
	if comp, ok := details["company"].(map[string]interface{}); ok {
		myWeekly = int64(comp["weekly_income"].(float64))
		myDaily = int64(comp["daily_income"].(float64))
		myDailyCustomers = int64(comp["daily_customers"].(float64))
		myWeeklyCustomers = int64(comp["weekly_customers"].(float64))
	}

	// Build same-tier and lower-tier slices
	type comp struct {
		Rating       int64
		WeeklyIncome int64
	}
	var sameTier []comp
	var lowerTier []comp

	if compMap, ok := list["company"].(map[string]interface{}); ok {
		if companies, ok := compMap["companies"].([]interface{}); ok {
			for _, cRaw := range companies {
				cMap := cRaw.(map[string]interface{})
				c := comp{
					Rating:       int64(cMap["rating"].(float64)),
					WeeklyIncome: int64(cMap["weekly_income"].(float64)),
				}
				if c.Rating == int64(myRating) {
					sameTier = append(sameTier, c)
				} else if c.Rating == int64(myRating)-1 {
					lowerTier = append(lowerTier, c)
				}
			}
		}
	}

	// Rank within tier
	rank := 1
	for _, c := range sameTier {
		if c.WeeklyIncome > myWeekly {
			rank++
		}
	}
	totalInTier := len(sameTier)
	belowMe := totalInTier - rank

	// Lowest income in tier
	lowestInTier := int64(0)
	for i, c := range sameTier {
		if i == 0 || c.WeeklyIncome < lowestInTier {
			lowestInTier = c.WeeklyIncome
		}
	}
	myMargin := myWeekly - lowestInTier

	// Lower tier analysis
	threatening := 0
	highestLower := int64(0)
	for _, c := range lowerTier {
		if c.WeeklyIncome > lowestInTier {
			threatening++
		}
		if c.WeeklyIncome > highestLower {
			highestLower = c.WeeklyIncome
		}
	}

	// Risk calculation
	pctBelow := 0.0
	if totalInTier > 0 {
		pctBelow = float64(belowMe) / float64(totalInTier) * 100.0
	}
	var risk string
	switch {
	case pctBelow > 20:
		risk = "LOW"
	case pctBelow >= 5 && threatening == 0:
		risk = "MEDIUM"
	case pctBelow < 5 || threatening > 0:
		risk = "HIGH"
	default:
		risk = "MEDIUM"
	}
	riskEmoji := map[string]string{"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🚨"}[risk]
	isSunday := time.Now().Weekday() == time.Sunday

	// Build report string
	var buf bytes.Buffer
	fmt.Fprintf(&buf, "═══ Torn Company Status ═══\n")
	fmt.Fprintf(&buf, "Company: %s (%d★)\n", myName, myRating)
	fmt.Fprintf(&buf, "Weekly Income: $%d | Daily: $%d\n", myWeekly, myDaily)
	fmt.Fprintf(&buf, "Daily Customers: %d | Weekly: %d\n", myDailyCustomers, myWeeklyCustomers)
	fmt.Fprintf(&buf, "\n── Your Position (%d★ tier) ──\n", myRating)
	fmt.Fprintf(&buf, "Rank: #%d / %d\n", rank, totalInTier)
	fmt.Fprintf(&buf, "Shops below you: %d\n", belowMe)
	fmt.Fprintf(&buf, "Lowest %d★ income: $%d\n", myRating, lowestInTier)
	fmt.Fprintf(&buf, "Your margin above floor: $%d\n", myMargin)
	fmt.Fprintf(&buf, "\n── Pressure from Below (%d★) ──\n", myRating-1)
	fmt.Fprintf(&buf, "%d★ shops earning more than lowest %d★: %d\n", myRating-1, lowestInTier, threatening)
	fmt.Fprintf(&buf, "Highest %d★ income: $%d\n", myRating-1, highestLower)
	fmt.Fprintf(&buf, "\n── Risk Assessment ──\n")
	fmt.Fprintf(&buf, "%s %s risk of starring down\n", riskEmoji, risk)
	fmt.Fprintf(&buf, "\n")
	if isSunday {
		fmt.Fprintf(&buf, "⚠️  Rating changes happen TODAY!\n")
	} else {
		fmt.Fprintf(&buf, "Next rating change: Sunday\n")
	}
	return buf.String(), nil
}
