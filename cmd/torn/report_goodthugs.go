package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"time"

	"github.com/spf13/cobra"
)

type goodThug struct {
	memberInfo
	OCCount int
}

// classifyThugs splits a list of Thugs into those who have completed at least one OC
// within the lookback window (ready for promotion) and those who have not.
func classifyThugs(thugs []memberInfo, ocCount map[int]int) (ready []goodThug, notYet []memberInfo) {
	for _, t := range thugs {
		count := ocCount[t.ID]
		if count > 0 {
			ready = append(ready, goodThug{memberInfo: t, OCCount: count})
		} else {
			notYet = append(notYet, t)
		}
	}
	return ready, notYet
}

// newGoodThugsCmd returns the "goodthugs" subcommand that identifies Thugs ready for promotion.
func newGoodThugsCmd() *cobra.Command {
	var days int

	cmd := &cobra.Command{
		Use:   "goodthugs",
		Short: "Report Thugs who have completed at least one OC and are ready for promotion",
		Long: `Identifies faction members with the "Thug" position who have completed
at least one organized crime. These members have earned armory access
and are ready to be promoted to Henchman.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			apiKey, err := getAPIKey(cmd)
			if err != nil {
				return err
			}
			return runGoodThugsReport(apiKey, days)
		},
	}

	cmd.Flags().IntVar(&days, "days", 14, "Lookback window in days for completed crimes")
	return cmd
}

// runGoodThugsReport finds Thugs who have completed at least one OC within the lookback window.
func runGoodThugsReport(apiKey string, days int) error {
	from := time.Now().Unix() - int64(days)*24*3600

	// Step 1: Fetch faction members, filter to Thugs
	fmt.Fprintf(os.Stderr, "Fetching faction members...\n")
	membersPages, err := fetchAllPages(apiKey, "https://api.torn.com/v2/faction/members")
	if err != nil {
		return fmt.Errorf("failed to fetch members: %w", err)
	}

	var thugs []memberInfo
	for _, page := range membersPages {
		var resp MembersPage
		if err := json.Unmarshal(page, &resp); err != nil {
			continue
		}
		for _, m := range resp.Members {
			if m.Position != "Thug" {
				continue
			}
			thugs = append(thugs, memberInfo{
				ID:            m.ID,
				Name:          m.Name,
				Level:         m.Level,
				Position:      m.Position,
				DaysInFaction: m.DaysInFaction,
				IsInOC:        m.IsInOC,
			})
		}
	}

	// Step 2: Fetch completed crimes within the lookback window
	fmt.Fprintf(os.Stderr, "Fetching completed crimes (last %d days)...\n", days)
	completedURL := fmt.Sprintf("https://api.torn.com/v2/faction/crimes?cat=completed&from=%d", from)
	completedPages, err := fetchAllPages(apiKey, completedURL)
	if err != nil {
		return fmt.Errorf("failed to fetch completed crimes: %w", err)
	}

	ocCount := make(map[int]int) // user ID -> number of completed OCs
	for _, page := range completedPages {
		var resp CrimesPage
		if err := json.Unmarshal(page, &resp); err != nil {
			continue
		}
		for _, crime := range resp.Crimes {
			for _, slot := range crime.Slots {
				if slot.User != nil && slot.User.ID > 0 {
					ocCount[int(slot.User.ID)]++
				}
			}
		}
	}

	// Step 3: Split thugs into ready vs not-yet
	ready, notYet := classifyThugs(thugs, ocCount)

	// Sort ready by OC count descending, then by name
	sort.Slice(ready, func(i, j int) bool {
		if ready[i].OCCount != ready[j].OCCount {
			return ready[i].OCCount > ready[j].OCCount
		}
		return ready[i].Name < ready[j].Name
	})

	// Sort not-yet by days in faction descending
	sort.Slice(notYet, func(i, j int) bool {
		return notYet[i].DaysInFaction > notYet[j].DaysInFaction
	})

	// Step 4: Print report
	fmt.Printf("\nGOOD THUGS (completed at least 1 OC, ready for promotion)\n")
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-20s %5s %7s %6s %6s\n", "Name", "OCs", "Level", "Days", "In OC")
	fmt.Println("------------------------------------------------------------")

	for _, r := range ready {
		inOC := "No"
		if r.IsInOC {
			inOC = "Yes"
		}
		fmt.Printf("%-20s %5d %7d %6d %6s\n",
			r.Name, r.OCCount, r.Level, r.DaysInFaction, inOC)
	}

	fmt.Printf("\nNOT YET (no completed OCs)\n")
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-20s %7s %6s %6s\n", "Name", "Level", "Days", "In OC")
	fmt.Println("------------------------------------------------------------")

	for _, t := range notYet {
		inOC := "No"
		if t.IsInOC {
			inOC = "Yes"
		}
		fmt.Printf("%-20s %7d %6d %6s\n",
			t.Name, t.Level, t.DaysInFaction, inOC)
	}

	fmt.Println()
	fmt.Printf("Ready for promotion: %d thugs\n", len(ready))
	fmt.Printf("Still waiting: %d thugs\n", len(notYet))

	return nil
}
