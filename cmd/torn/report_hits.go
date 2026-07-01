package main

import (
	"fmt"
	"os"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
	"github.com/spf13/cobra"
)

func newHitsCmd(hitService *services.HitService) *cobra.Command {
	var name string
	var days int

	cmd := &cobra.Command{
		Use:   "hits",
		Short: "Report outgoing hits for a faction member",
		Long: `Lists all outgoing attacks by a named faction member within a time window,
with results, defenders, respect gained, and links to attack logs.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if name == "" {
				return fmt.Errorf("--name is required")
			}
			return runHitsReport(cmd, name, days, hitService)
		},
	}

	cmd.Flags().StringVar(&name, "name", "", "Faction member's in-game name (required)")
	cmd.Flags().IntVar(&days, "days", 7, "Lookback window in days")
	return cmd
}

func runHitsReport(cmd *cobra.Command, name string, days int, svc *services.HitService) error {
	from := time.Now().AddDate(0, 0, -days)
	fmt.Fprintf(os.Stderr, "Fetching outgoing attacks since %s...\n",
		from.UTC().Format("2006-01-02 15:04 UTC"))

	hits, err := svc.GetAttackHistory(cmd.Context(), name, days)
	if err != nil {
		return fmt.Errorf("failed to fetch attacks: %w", err)
	}

	fmt.Printf("\nHITS for %s — last %d days (%d total)\n", name, days, len(hits))
	fmt.Println("--------------------------------------------------------------------------------------------")
	fmt.Printf("%-19s  %-12s  %-22s  %6s  %s\n", "Time (UTC)", "Result", "Defender", "Resp", "Link")
	fmt.Println("--------------------------------------------------------------------------------------------")

	for _, h := range hits {
		dateTime := time.Unix(h.Timestamp, 0).UTC().Format("2006-01-02 15:04 UTC")
		respStr := fmt.Sprintf("%+.2f", h.RespectGain)
		if h.RespectGain == 0 {
			respStr = "  0.00"
		}
		linkStr := h.Link
		if linkStr == "" {
			linkStr = "-"
		}
		fmt.Printf("%-19s  %-12s  %-22s  %6s  %s\n",
			dateTime, h.Result, h.Defender, respStr, linkStr)
	}

	fmt.Println()
	fmt.Printf("%d hits for %s in the last %d days\n", len(hits), name, days)
	return nil
}
