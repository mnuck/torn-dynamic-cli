package main

import (
	"fmt"
	"os"
	"regexp"
	"sort"
	"time"

	"github.com/spf13/cobra"
	"github.com/tidwall/gjson"
)

// newFreeloadersCmd returns the "freeloaders" subcommand that checks Xanax usage vs OC participation.
func newFreeloadersCmd() *cobra.Command {
	var hours int

	cmd := &cobra.Command{
		Use:   "freeloaders",
		Short: "Report members who used faction Xanax but aren't in OCs",
		Long: `Identifies faction members who consumed Xanax from the faction armory
but are not currently participating in organized crimes.

This helps identify members who are not contributing to the faction's OC efforts
despite using shared resources.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			apiKey, err := getAPIKey(cmd)
			if err != nil {
				return err
			}
			return runFreeloadersReport(apiKey, hours)
		},
	}

	cmd.Flags().IntVar(&hours, "hours", 48, "Lookback window in hours for armory and crime checks")
	return cmd
}

// runFreeloadersReport executes the freeloader detection logic.
func runFreeloadersReport(apiKey string, hours int) error {
	from := time.Now().Unix() - int64(hours*3600)

	// Step 1: Fetch faction members to build name→ID map and member metadata
	fmt.Fprintf(os.Stderr, "Fetching faction members...\n")
	membersPages, err := fetchAllPages(apiKey, "https://api.torn.com/v2/faction/members")
	if err != nil {
		return fmt.Errorf("failed to fetch members: %w", err)
	}

	nameToID := make(map[string]int)
	memberData := make(map[int]memberInfo)

	for _, page := range membersPages {
		members := gjson.GetBytes(page, "members").Array()
		for _, m := range members {
			id := int(m.Get("id").Int())
			name := m.Get("name").String()
			nameToID[name] = id
			memberData[id] = memberInfo{
				ID:            id,
				Name:          name,
				Level:         int(m.Get("level").Int()),
				Position:      m.Get("position").String(),
				DaysInFaction: int(m.Get("days_in_faction").Int()),
				IsInOC:        m.Get("is_in_oc").Bool(),
			}
		}
	}

	// Step 2: Fetch faction news to find Xanax usage
	fmt.Fprintf(os.Stderr, "Fetching faction news (armory actions)...\n")
	newsURL := fmt.Sprintf("https://api.torn.com/v2/faction/news?cat=armoryAction&striptags=true&from=%d", from)
	newsPages, err := fetchAllPages(apiKey, newsURL)
	if err != nil {
		return fmt.Errorf("failed to fetch news: %w", err)
	}

	// Regex matches "Username used one of the faction's Xanax items"
	// The striptags=true parameter gives us plain text without HTML
	xanaxPattern := regexp.MustCompile(`^(\S+) used one of the faction's Xanax items$`)
	xanaxUsage := make(map[string]int)

	for _, page := range newsPages {
		news := gjson.GetBytes(page, "news").Array()
		for _, item := range news {
			text := item.Get("text").String()
			if matches := xanaxPattern.FindStringSubmatch(text); matches != nil {
				username := matches[1]
				xanaxUsage[username]++
			}
		}
	}

	// Step 3a: Fetch active crimes (recruiting/planning) — no time filter
	// Anyone sitting in a slot right now is participating
	fmt.Fprintf(os.Stderr, "Fetching active crimes...\n")
	activePages, err := fetchAllPages(apiKey, "https://api.torn.com/v2/faction/crimes?cat=available")
	if err != nil {
		return fmt.Errorf("failed to fetch active crimes: %w", err)
	}

	ocParticipants := make(map[int]bool)

	for _, page := range activePages {
		crimes := gjson.GetBytes(page, "crimes").Array()
		for _, crime := range crimes {
			for _, slot := range crime.Get("slots").Array() {
				if uid := slot.Get("user.id").Int(); uid > 0 {
					ocParticipants[int(uid)] = true
				}
			}
		}
	}

	// Step 3b: Fetch completed crimes with 14-day buffer before the lookback window
	// The API's `from` param likely filters on created_at, not executed_at.
	// A crime created 5 days ago but executed today would be missed without the buffer.
	// We fetch with a wider net then client-side filter on executed_at.
	fmt.Fprintf(os.Stderr, "Fetching completed crimes...\n")
	crimeFrom := from - 14*24*3600 // 14-day buffer for long-running crimes
	completedURL := fmt.Sprintf("https://api.torn.com/v2/faction/crimes?cat=completed&from=%d", crimeFrom)
	completedPages, err := fetchAllPages(apiKey, completedURL)
	if err != nil {
		return fmt.Errorf("failed to fetch completed crimes: %w", err)
	}

	for _, page := range completedPages {
		crimes := gjson.GetBytes(page, "crimes").Array()
		for _, crime := range crimes {
			executedAt := crime.Get("executed_at").Int()
			if executedAt < from {
				continue // completed before our actual lookback window
			}
			for _, slot := range crime.Get("slots").Array() {
				if uid := slot.Get("user.id").Int(); uid > 0 {
					ocParticipants[int(uid)] = true
				}
			}
		}
	}

	// Step 4: Cross-reference to identify freeloaders
	type freeloader struct {
		Name          string
		XanaxCount    int
		Level         int
		Position      string
		DaysInFaction int
	}

	var freeloaders []freeloader
	compliantCount := 0
	totalXanax := 0

	for username, count := range xanaxUsage {
		totalXanax += count
		userID, exists := nameToID[username]
		if !exists {
			// Username not found in member list - possibly left faction
			continue
		}

		member := memberData[userID]
		inOC := ocParticipants[userID] || member.IsInOC

		if !inOC {
			freeloaders = append(freeloaders, freeloader{
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

	// Sort freeloaders by Xanax usage (descending), then by name
	sort.Slice(freeloaders, func(i, j int) bool {
		if freeloaders[i].XanaxCount != freeloaders[j].XanaxCount {
			return freeloaders[i].XanaxCount > freeloaders[j].XanaxCount
		}
		return freeloaders[i].Name < freeloaders[j].Name
	})

	// Step 5: Print report
	fmt.Printf("\nFREELOADERS (used faction Xanax in last %dh, not in any OC)\n", hours)
	fmt.Println("------------------------------------------------------------")
	fmt.Printf("%-20s %5s %7s  %-16s %4s\n", "Name", "Xanax", "Level", "Position", "Days")
	fmt.Println("------------------------------------------------------------")

	for _, f := range freeloaders {
		fmt.Printf("%-20s %5d %7d  %-16s %4d\n",
			f.Name, f.XanaxCount, f.Level, f.Position, f.DaysInFaction)
	}

	fmt.Println()
	fmt.Printf("Compliant: %d members used Xanax and are in OCs\n", compliantCount)
	fmt.Printf("Freeloaders: %d members used Xanax without OC participation\n", len(freeloaders))
	fmt.Printf("Total Xanax used from supply: %d\n", totalXanax)

	return nil
}

