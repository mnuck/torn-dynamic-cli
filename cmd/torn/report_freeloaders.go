package main

import (
	"context"
	"fmt"
	"sort"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
	"github.com/spf13/cobra"
)

func newFreeloadersCmd(freeloaderService *services.FreeloaderService) *cobra.Command {
	var hours int

	cmd := &cobra.Command{
		Use:   "freeloaders",
		Short: "Report members who used faction Xanax but aren't in OCs",
		Long: `Identifies faction members who consumed Xanax from the faction armory
but are not currently participating in organized crimes.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			return runFreeloadersReport(cmd.Context(), hours, freeloaderService)
		},
	}

	cmd.Flags().IntVar(&hours, "hours", 48, "Lookback window in hours for armory and crime checks")
	return cmd
}

func runFreeloadersReport(ctx context.Context, hours int, svc *services.FreeloaderService) error {
	freeloaders, compliantCount, err := svc.IdentifyFreeloaders(ctx, hours)
	if err != nil {
		return fmt.Errorf("failed to identify freeloaders: %w", err)
	}

	sort.Slice(freeloaders, func(i, j int) bool {
		if freeloaders[i].XanaxCount != freeloaders[j].XanaxCount {
			return freeloaders[i].XanaxCount > freeloaders[j].XanaxCount
		}
		return freeloaders[i].Name < freeloaders[j].Name
	})

	totalXanax := 0
	for _, f := range freeloaders {
		totalXanax += f.XanaxCount
	}

	fmt.Printf("\nFREELOADERS (used faction Xanax in last %dh, not in any OC)\n", hours)
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-20s %5s %7s  %-16s %4s\n", "Name", "Xanax", "Level", "Position", "Days")
	fmt.Println("------------------------------------------------------------")

	for _, f := range freeloaders {
		fmt.Printf("%-20s %5d %7d  %-16s %4d\n",
			f.Name, f.XanaxCount, f.Level, f.Position, f.DaysInFaction)
	}

	fmt.Println()
	fmt.Printf("Compliant:   %d members used Xanax and are in OCs\n", compliantCount)
	fmt.Printf("Freeloaders: %d members used Xanax without OC participation\n", len(freeloaders))
	fmt.Printf("Total Xanax used from supply: %d\n", totalXanax)
	return nil
}

// classifyFreeloaders is kept for use in tests that import it directly.
func classifyFreeloaders(
	xanaxUsage map[string]int,
	nameToID map[string]int,
	memberData map[int]memberInfo,
	ocParticipants map[int]bool,
) ([]domain.Freeloader, int) {
	var freeloaders []domain.Freeloader
	compliantCount := 0

	for username, count := range xanaxUsage {
		userID, exists := nameToID[username]
		if !exists {
			continue
		}
		member := memberData[userID]
		inOC := ocParticipants[userID] || member.IsInOC
		if !inOC {
			freeloaders = append(freeloaders, domain.Freeloader{
				Name:          username,
				XanaxCount:    count,
				Level:         member.Level,
				Position:      member.Position,
				DaysInFaction: member.DaysInFaction,
			})
		} else {
			compliantCount++
		}
	}
	return freeloaders, compliantCount
}
