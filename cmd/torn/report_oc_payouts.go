package main

import (
	"fmt"
	"os"
	"sort"
	"time"

	"github.com/spf13/cobra"
	"github.com/tidwall/gjson"
)

func newOCPayoutsCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "oc-payouts",
		Short: "List completed OCs awaiting payout",
		Long: `Shows all completed OCs that have not yet been paid out.

For each unpaid OC, indicates whether everyone was on time (safe to use the
normal slider percentage) or whether the OC was delayed more than 30 minutes
(someone may need to be withheld — run 'report late-ocs --hours N' to identify who).

OCs with scope=0 are skipped — these are stepping-stone crimes that spawn a
higher-level OC rather than paying out directly.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			apiKey, err := getAPIKey(cmd)
			if err != nil {
				return err
			}
			return runOCPayoutsReport(apiKey)
		},
	}
	return cmd
}

type unpaidOC struct {
	ID         int64
	Name       string
	ReadyAt    int64
	ExecutedAt int64
	DelaySec   int64
	Money      int64
	Respect    int64
	Status     string
	Slots      []ocSlot
}

func runOCPayoutsReport(apiKey string) error {
	fmt.Fprintf(os.Stderr, "Fetching completed crimes...\n")

	body, err := fetchSinglePage(apiKey, "https://api.torn.com/v2/faction/crimes?cat=completed")
	if err != nil {
		return fmt.Errorf("failed to fetch completed crimes: %w", err)
	}

	var unpaid []unpaidOC

	crimes := gjson.GetBytes(body, "crimes").Array()
	for _, c := range crimes {
		rewards := c.Get("rewards")
		if !rewards.Exists() {
			continue
		}

		// scope=0 means this OC spawns a higher-level crime rather than paying out.
		// These are intentionally $0 and should be excluded from payout tracking.
		scope := rewards.Get("scope").Int()
		if scope == 0 {
			continue
		}

		// Already paid out — skip
		if rewards.Get("payout").Exists() && rewards.Get("payout").Type != gjson.Null {
			continue
		}

		executedAt := c.Get("executed_at").Int()
		if executedAt == 0 {
			continue // not yet executed (still planning/running)
		}

		readyAt := c.Get("ready_at").Int()

		var slots []ocSlot
		for _, s := range c.Get("slots").Array() {
			slots = append(slots, ocSlot{
				Position: s.Get("position_info.label").String(),
				UserID:   s.Get("user.id").Int(),
			})
		}

		unpaid = append(unpaid, unpaidOC{
			ID:         c.Get("id").Int(),
			Name:       c.Get("name").String(),
			ReadyAt:    readyAt,
			ExecutedAt: executedAt,
			DelaySec:   executedAt - readyAt,
			Money:      rewards.Get("money").Int(),
			Respect:    rewards.Get("respect").Int(),
			Status:     c.Get("status").String(),
			Slots:      slots,
		})
	}

	if len(unpaid) == 0 {
		fmt.Println("No unpaid OCs found.")
		return nil
	}

	// Sort by executed_at ascending (oldest first — pay those first)
	sort.Slice(unpaid, func(i, j int) bool {
		return unpaid[i].ExecutedAt < unpaid[j].ExecutedAt
	})

	// Look up member names in parallel for all OCs
	fmt.Fprintf(os.Stderr, "Looking up member names...\n")
	for i := range unpaid {
		if len(unpaid[i].Slots) > 0 {
			lookupSlotProfiles(apiKey, unpaid[i].Slots)
		}
	}

	// Print report
	fmt.Printf("\nUNPAID OCs (%d)\n", len(unpaid))
	fmt.Println("================================================================================")

	for _, oc := range unpaid {
		execStr := time.Unix(oc.ExecutedAt, 0).UTC().Format("2006-01-02 15:04 UTC")
		link := fmt.Sprintf("https://www.torn.com/factions.php?step=your&type=1#/tab=crimes&crimeId=%d", oc.ID)

		// Determine payout verdict
		const lateThreshold = 30 * 60 // 30 minutes in seconds
		var verdict string
		if oc.DelaySec > lateThreshold {
			verdict = fmt.Sprintf("⚠️  DELAYED %s — check who was blocking before paying", formatDuration(oc.DelaySec))
		} else {
			verdict = "✅ Everyone on time — safe to pay at normal percentage"
		}

		// Format money
		moneyStr := "-"
		if oc.Money > 0 {
			moneyStr = fmt.Sprintf("$%s", formatMoney(oc.Money))
		}

		fmt.Printf("\n%s (id=%d) [%s]\n", oc.Name, oc.ID, oc.Status)
		fmt.Printf("  Executed: %s | Money: %s | Respect: %d\n", execStr, moneyStr, oc.Respect)
		fmt.Printf("  %s\n", verdict)
		fmt.Printf("  Link: %s\n", link)
		fmt.Printf("  Members: ")
		for i, s := range oc.Slots {
			name := s.UserName
			if name == "" {
				name = fmt.Sprintf("uid:%d", s.UserID)
			}
			if i > 0 {
				fmt.Print(", ")
			}
			fmt.Printf("%s (%s)", name, s.Position)
		}
		fmt.Println()
	}

	fmt.Println("\n================================================================================")
	fmt.Printf("%d OC(s) awaiting payout\n", len(unpaid))
	return nil
}

// formatMoney formats a large integer as a comma-separated string (e.g. 1234567 -> "1,234,567").
func formatMoney(n int64) string {
	s := fmt.Sprintf("%d", n)
	result := []byte{}
	for i, c := range s {
		if i > 0 && (len(s)-i)%3 == 0 {
			result = append(result, ',')
		}
		result = append(result, byte(c))
	}
	return string(result)
}
