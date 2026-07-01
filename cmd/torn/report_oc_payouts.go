package main

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
	"github.com/spf13/cobra"
)

func newOCPayoutsCmd(svc *services.OCPayoutService, client ports.TornClient) *cobra.Command {
	return &cobra.Command{
		Use:   "oc-payouts",
		Short: "List completed OCs awaiting payout",
		Long: `Shows all completed OCs that have not yet been paid out.

For each unpaid OC, indicates whether everyone was on time (safe to use the
normal slider percentage) or whether the OC was delayed more than 30 minutes
(someone may need to be withheld — run 'report late-ocs --hours N' to identify who).

OCs with scope=0 are skipped — these are stepping-stone crimes that spawn a
higher-level OC rather than paying out directly.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			return runOCPayoutsReport(cmd.Context(), svc, client)
		},
	}
}

func runOCPayoutsReport(ctx context.Context, svc *services.OCPayoutService, client ports.TornClient) error {
	unpaid, err := svc.GetUnpaidOCs(ctx)
	if err != nil {
		return fmt.Errorf("failed to fetch unpaid OCs: %w", err)
	}

	if len(unpaid) == 0 {
		fmt.Println("No unpaid OCs found.")
		return nil
	}

	// Resolve slot names concurrently
	resolveNames(ctx, unpaid, client)

	fmt.Printf("\nUNPAID OCs (%d)\n", len(unpaid))
	fmt.Println("================================================================================")

	for _, oc := range unpaid {
		execStr := oc.Crime.ExecutedAt.UTC().Format("2006-01-02 15:04 UTC")
		link := fmt.Sprintf("https://www.torn.com/factions.php?step=your&type=1#/tab=crimes&crimeId=%d", oc.Crime.ID)

		var verdict string
		if oc.IsLate {
			verdict = fmt.Sprintf("⚠️  DELAYED %s — check who was blocking before paying", fmtDuration(oc.DelaySec))
		} else {
			verdict = "✅ Everyone on time — safe to pay at normal percentage"
		}

		moneyStr := "-"
		if oc.Crime.Rewards.Money > 0 {
			moneyStr = fmt.Sprintf("$%s", fmtMoney(int64(oc.Crime.Rewards.Money)))
		}

		fmt.Printf("\n%s (id=%d) [%s]\n", oc.Crime.Name, oc.Crime.ID, oc.Crime.Status)
		fmt.Printf("  Executed: %s | Money: %s | Respect: %d\n", execStr, moneyStr, oc.Crime.Rewards.Respect)
		fmt.Printf("  %s\n", verdict)
		fmt.Printf("  Link: %s\n", link)
		fmt.Printf("  Members:")
		for i, s := range oc.Crime.Slots {
			name := fmt.Sprintf("uid:%d", 0)
			label := s.Label
			if s.User != nil {
				name = s.User.Name
				if name == "" {
					name = fmt.Sprintf("uid:%d", s.User.ID)
				}
			}
			if i == 0 {
				fmt.Printf(" ")
			} else {
				fmt.Printf(", ")
			}
			fmt.Printf("%s (%s)", name, label)
		}
		fmt.Println()
	}

	fmt.Println("\n================================================================================")
	fmt.Printf("%d OC(s) awaiting payout\n", len(unpaid))
	return nil
}

// resolveNames fills in User.Name for all slots by calling GetUser concurrently.
func resolveNames(ctx context.Context, unpaid []services.UnpaidOC, client ports.TornClient) {
	var wg sync.WaitGroup
	var mu sync.Mutex

	// Collect unique IDs
	seen := make(map[int]bool)
	names := make(map[int]string)
	for _, oc := range unpaid {
		for _, s := range oc.Crime.Slots {
			if s.User != nil && s.User.ID > 0 && !seen[s.User.ID] {
				seen[s.User.ID] = true
				wg.Add(1)
				go func(id int) {
					defer wg.Done()
					user, err := client.GetUser(ctx, id)
					if err != nil || user == nil {
						return
					}
					mu.Lock()
					names[id] = user.Name
					mu.Unlock()
				}(s.User.ID)
			}
		}
	}
	wg.Wait()

	// Patch names back into the slots
	for i := range unpaid {
		for j := range unpaid[i].Crime.Slots {
			if s := unpaid[i].Crime.Slots[j].User; s != nil {
				if n, ok := names[s.ID]; ok {
					unpaid[i].Crime.Slots[j].User.Name = n
				}
			}
		}
	}
}

func fmtDuration(seconds int64) string {
	if seconds < 60 {
		return fmt.Sprintf("%ds", seconds)
	}
	if seconds < 3600 {
		return fmt.Sprintf("%dm%02ds", seconds/60, seconds%60)
	}
	return fmt.Sprintf("%dh%02dm", seconds/3600, (seconds%3600)/60)
}

func fmtMoney(n int64) string {
	s := fmt.Sprintf("%d", n)
	result := make([]byte, 0, len(s)+len(s)/3)
	for i, c := range s {
		if i > 0 && (len(s)-i)%3 == 0 {
			result = append(result, ',')
		}
		result = append(result, byte(c))
	}
	return string(result)
}

// Ensure time import is used.
var _ = time.Time{}
