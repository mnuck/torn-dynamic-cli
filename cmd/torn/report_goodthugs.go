package main

import (
	"fmt"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
	"github.com/spf13/cobra"
)

func newGoodThugsCmd(svc *services.GoodThugService) *cobra.Command {
	var days int

	cmd := &cobra.Command{
		Use:   "goodthugs",
		Short: "Report Thugs who have completed at least one OC and are ready for promotion",
		Long: `Identifies faction members with the "Thug" position who have completed
at least one organized crime. These members have earned armory access
and are ready to be promoted to Henchman.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			return runGoodThugsReport(cmd, days, svc)
		},
	}

	cmd.Flags().IntVar(&days, "days", 14, "Lookback window in days for completed crimes")
	return cmd
}

func runGoodThugsReport(cmd *cobra.Command, days int, svc *services.GoodThugService) error {
	report, err := svc.Analyze(cmd.Context(), days)
	if err != nil {
		return fmt.Errorf("failed to generate goodthugs report: %w", err)
	}

	fmt.Printf("\nGOOD THUGS (completed at least 1 OC, ready for promotion)\n")
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-20s %5s %7s %6s %6s\n", "Name", "OCs", "Level", "Days", "In OC")
	fmt.Println("------------------------------------------------------------")
	for _, r := range report.Ready {
		inOC := "No"
		if r.IsInOC {
			inOC = "Yes"
		}
		fmt.Printf("%-20s %5d %7d %6d %6s\n", r.Name, r.OCCount, r.Level, r.DaysInFaction, inOC)
	}

	fmt.Printf("\nNOT YET (no completed OCs)\n")
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-20s %7s %6s %6s\n", "Name", "Level", "Days", "In OC")
	fmt.Println("------------------------------------------------------------")
	for _, t := range report.NotYet {
		inOC := "No"
		if t.IsInOC {
			inOC = "Yes"
		}
		fmt.Printf("%-20s %7d %6d %6s\n", t.Name, t.Level, t.DaysInFaction, inOC)
	}

	fmt.Println()
	fmt.Printf("Ready for promotion: %d thugs\n", len(report.Ready))
	fmt.Printf("Still waiting:       %d thugs\n", len(report.NotYet))
	return nil
}
