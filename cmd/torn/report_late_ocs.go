package main

import (
	"context"
	"fmt"
	"os"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
	"github.com/spf13/cobra"
)

func newLateOCsCmd(svc *services.LateOCService) *cobra.Command {
	var hours int

	cmd := &cobra.Command{
		Use:   "late-ocs",
		Short: "Find organized crimes that are late starting",
		Long: `Identifies OCs where ready_at has passed but the crime hasn't executed yet.
Shows who is currently blocking each late OC (abroad, hospital, jail, traveling).

Use --hours to also include OCs that were late but have since executed.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			return runLateOCsReport(cmd.Context(), hours, svc)
		},
	}

	cmd.Flags().IntVar(&hours, "hours", 0, "Also look back N hours for OCs that were late (0 = current only)")
	return cmd
}

func runLateOCsReport(ctx context.Context, hours int, svc *services.LateOCService) error {
	fmt.Fprintf(os.Stderr, "Fetching faction crimes...\n")

	lateOCs, err := svc.FindLateOCs(ctx, hours)
	if err != nil {
		return fmt.Errorf("failed to find late OCs: %w", err)
	}

	if len(lateOCs) == 0 {
		fmt.Println("No late OCs found.")
		return nil
	}

	for _, oc := range lateOCs {
		delayStr := formatDuration(oc.DelaySec)
		readyStr := oc.ReadyAt.UTC().Format("2006-01-02 15:04 UTC")

		if oc.ExecutedAt != nil {
			execStr := oc.ExecutedAt.UTC().Format("2006-01-02 15:04 UTC")
			fmt.Printf("\n%s (id=%d) — %s late [EXECUTED]\n", oc.Name, oc.ID, delayStr)
			fmt.Printf("  Ready: %s | Executed: %s\n", readyStr, execStr)
			if len(oc.Slots) > 0 {
				printSlotMembers(oc.Slots)
			}
		} else {
			fmt.Printf("\n%s (id=%d) — %s late [STILL WAITING]\n", oc.Name, oc.ID, delayStr)
			fmt.Printf("  Ready: %s\n", readyStr)
			printSlotTable(oc.Slots)
		}
	}

	fmt.Println()
	return nil
}

// printSlotMembers prints a compact member list for historical OCs.
func printSlotMembers(slots []domain.LateOCSlot) {
	fmt.Print("  Members: ")
	for i, s := range slots {
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

// printSlotTable prints the full status table for still-waiting OCs, marking blockers with ▶.
func printSlotTable(slots []domain.LateOCSlot) {
	fmt.Printf("  %-20s  %-18s  %-8s  %-30s  %s\n",
		"Position", "Member", "Item", "Status", "Last Active")
	fmt.Printf("  %-20s  %-18s  %-8s  %-30s  %s\n",
		"--------------------", "------------------", "--------",
		"------------------------------", "-----------")

	for _, s := range slots {
		name := s.UserName
		if name == "" {
			name = fmt.Sprintf("uid:%d", s.UserID)
		}

		status := s.StatusState
		if s.StatusDesc != "" && s.StatusDesc != "Okay" {
			status = fmt.Sprintf("%s — %s", s.StatusState, s.StatusDesc)
		}

		marker := "  "
		if s.IsBlocker {
			marker = "▶ "
		}

		fmt.Printf("%s%-20s  %-18s  %-8s  %-30s  %s\n",
			marker, s.Position, name, s.ItemAvailable, status, s.LastAction)
	}
}

// formatDuration renders a second count as a compact human string (e.g. "1h 30m").
func formatDuration(seconds int64) string {
	if seconds < 60 {
		return fmt.Sprintf("%ds", seconds)
	}
	minutes := seconds / 60
	if minutes < 60 {
		return fmt.Sprintf("%dm", minutes)
	}
	hours := minutes / 60
	mins := minutes % 60
	if mins == 0 {
		return fmt.Sprintf("%dh", hours)
	}
	return fmt.Sprintf("%dh %dm", hours, mins)
}
