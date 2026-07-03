package main

import (
	"context"
	"fmt"
	"os"
	"sort"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
	"github.com/spf13/cobra"
)

func newOCRiskCmd(client ports.TornClient) *cobra.Command {
	return &cobra.Command{
		Use:   "oc-risk",
		Short: "Predicts upcoming OCs at risk of being late",
		Long:  "Checks upcoming planning OCs for members who are currently Abroad, Traveling, in Hospital, or in Jail.",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runOCRiskReport(cmd.Context(), client)
		},
	}
}

func runOCRiskReport(ctx context.Context, client ports.TornClient) error {
	fmt.Fprintf(os.Stderr, "Fetching planning OCs and faction members...\n")

	// 1. Get upcoming planning OCs
	crimes, err := client.GetCrimes(ctx, "planning", nil)
	if err != nil {
		return fmt.Errorf("failed to get planning crimes: %w", err)
	}

	// 2. Get all faction members
	members, err := client.GetMembers(ctx)
	if err != nil {
		return fmt.Errorf("failed to get faction members: %w", err)
	}

	memberMap := make(map[int]domain.Member)
	for _, m := range members {
		memberMap[m.ID] = m
	}

	now := time.Now().UTC()
	cutoff := now.Add(6 * time.Hour)

	fmt.Println("\nUpcoming OCs at risk (next 6h):")
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-25s %-10s\n", "Name", "Ready at")
	fmt.Println("------------------------------------------------------------")

	foundRisk := false

	// Sort crimes by ready_at
	sort.Slice(crimes, func(i, j int) bool {
		return crimes[i].ReadyAt.Before(crimes[j].ReadyAt)
	})

	for _, crime := range crimes {
		if crime.ReadyAt.IsZero() || crime.ReadyAt.After(cutoff) || crime.ReadyAt.Before(now) {
			continue
		}

		var risks []string
		for _, slot := range crime.Slots {
			if slot.User == nil {
				continue
			}
			member, ok := memberMap[slot.User.ID]
			if !ok {
				continue
			}
			if member.Status.State != "" && member.Status.State != "Okay" {
				risks = append(risks, fmt.Sprintf("%s (%s)", member.Name, member.Status.Description))
			}
		}

		if len(risks) > 0 {
			foundRisk = true
			fmt.Printf("%-25s %-10s\n", crime.Name, crime.ReadyAt.Format("15:04 UTC"))
			for _, r := range risks {
				fmt.Printf("  └─ ⚠ %s\n", r)
			}
		}
	}

	if !foundRisk {
		fmt.Println("No upcoming OCs are currently at risk.")
	}

	return nil
}
