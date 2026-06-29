package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"sync"
	"time"

	"github.com/spf13/cobra"
)

func newLateOCsCmd() *cobra.Command {
	var hours int

	cmd := &cobra.Command{
		Use:   "late-ocs",
		Short: "Find organized crimes that are late starting",
		Long: `Identifies OCs where ready_at has passed but the crime hasn't executed yet.
Shows who is currently blocking each late OC (abroad, hospital, jail, traveling).

Use --hours to also include OCs that were late but have since executed.`,
		RunE: func(cmd *cobra.Command, args []string) error {
			apiKey, err := getAPIKey(cmd)
			if err != nil {
				return err
			}
			return runLateOCsReport(apiKey, hours)
		},
	}

	cmd.Flags().IntVar(&hours, "hours", 0, "Also look back N hours for OCs that were late (0 = current only)")
	return cmd
}

type lateOC struct {
	ID         int64
	Name       string
	ReadyAt    int64
	ExecutedAt int64
	DelaySec   int64
	Slots      []ocSlot
}

type ocSlot struct {
	Position    string
	UserID      int64
	UserName    string
	ItemAvail   string
	StatusState string
	StatusDesc  string
	LastAction  string
	IsBlocker   bool
}

func runLateOCsReport(apiKey string, hours int) error {
	now := time.Now().Unix()

	fmt.Fprintf(os.Stderr, "Fetching faction crimes...\n")

	// Always fetch planning for currently-late OCs
	planningBody, err := fetchSinglePage(apiKey, "https://api.torn.com/v2/faction/crimes?cat=planning")
	if err != nil {
		return fmt.Errorf("failed to fetch planning crimes: %w", err)
	}
	allCrimeData := [][]byte{planningBody}

	// For historical lookback, also fetch completed OCs
	if hours > 0 {
		completedBody, err := fetchSinglePage(apiKey, "https://api.torn.com/v2/faction/crimes?cat=completed")
		if err != nil {
			return fmt.Errorf("failed to fetch completed crimes: %w", err)
		}
		allCrimeData = append(allCrimeData, completedBody)
	}

	// Parse and find late OCs
	var lateOCs []lateOC
	cutoff := now - int64(hours)*3600

	for _, page := range allCrimeData {
		var resp CrimesPage
		if err := json.Unmarshal(page, &resp); err != nil {
			continue
		}
		for _, c := range resp.Crimes {
			if c.Status == "Recruiting" {
				continue
			}
			if c.ReadyAt == 0 {
				continue
			}

			if c.ExecutedAt > 0 {
				// Historical: was it meaningfully late and within our lookback window?
				// Require at least 5 minutes of delay to filter out normal execution jitter.
				if hours == 0 || c.ReadyAt >= now || (c.ExecutedAt-c.ReadyAt) < 300 || c.ReadyAt < cutoff {
					continue
				}
				loc := lateOC{
					ID:         c.ID,
					Name:       c.Name,
					ReadyAt:    c.ReadyAt,
					ExecutedAt: c.ExecutedAt,
					DelaySec:   c.ExecutedAt - c.ReadyAt,
				}
				for _, s := range c.Slots {
					slot := ocSlot{ItemAvail: formatItemAvail(s.ItemRequirement)}
					if s.PositionInfo != nil {
						slot.Position = s.PositionInfo.Label
					}
					if s.User != nil {
						slot.UserID = s.User.ID
					}
					loc.Slots = append(loc.Slots, slot)
				}
				lateOCs = append(lateOCs, loc)
			} else {
				// Currently late: ready_at in the past, not executed
				if c.ReadyAt >= now {
					continue
				}
				loc := lateOC{
					ID:       c.ID,
					Name:     c.Name,
					ReadyAt:  c.ReadyAt,
					DelaySec: now - c.ReadyAt,
				}
				for _, s := range c.Slots {
					slot := ocSlot{ItemAvail: formatItemAvail(s.ItemRequirement)}
					if s.PositionInfo != nil {
						slot.Position = s.PositionInfo.Label
					}
					if s.User != nil {
						slot.UserID = s.User.ID
					}
					loc.Slots = append(loc.Slots, slot)
				}
				lateOCs = append(lateOCs, loc)
			}
		}
	}

	if len(lateOCs) == 0 {
		fmt.Println("No late OCs found.")
		return nil
	}

	// Sort by delay descending
	sort.Slice(lateOCs, func(i, j int) bool {
		return lateOCs[i].DelaySec > lateOCs[j].DelaySec
	})

	// Look up member names (and current status for still-late OCs) in parallel
	for i := range lateOCs {
		if len(lateOCs[i].Slots) == 0 {
			continue
		}
		lookupSlotProfiles(apiKey, lateOCs[i].Slots)
	}

	// Print report
	for _, oc := range lateOCs {
		delayStr := formatDuration(oc.DelaySec)
		readyStr := time.Unix(oc.ReadyAt, 0).UTC().Format("2006-01-02 15:04 UTC")

		if oc.ExecutedAt > 0 {
			execStr := time.Unix(oc.ExecutedAt, 0).UTC().Format("2006-01-02 15:04 UTC")
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

// lookupSlotProfiles fetches user profiles for all slots concurrently.
func lookupSlotProfiles(apiKey string, slots []ocSlot) {
	var wg sync.WaitGroup
	var mu sync.Mutex

	for i := range slots {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			url := fmt.Sprintf("https://api.torn.com/v2/user/%d/profile", slots[idx].UserID)
			body, err := fetchSinglePage(apiKey, url)
			if err != nil {
				return
			}

			var resp ProfilePage
			if err := json.Unmarshal(body, &resp); err != nil || resp.Profile == nil {
				return
			}
			p := resp.Profile
			state, desc, lastAction := "", "", ""
			if p.Status != nil {
				state = p.Status.State
				desc = p.Status.Description
			}
			if p.LastAction != nil {
				lastAction = p.LastAction.Relative
			}

			mu.Lock()
			slots[idx].UserName = p.Name
			slots[idx].StatusState = state
			slots[idx].StatusDesc = desc
			slots[idx].LastAction = lastAction
			slots[idx].IsBlocker = state != "Okay"
			mu.Unlock()
		}(i)
	}
	wg.Wait()
}

// printSlotMembers prints a compact member list for historical OCs.
func printSlotMembers(slots []ocSlot) {
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

func printSlotTable(slots []ocSlot) {
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
			marker, s.Position, name, s.ItemAvail, status, s.LastAction)
	}
}

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

// fetchSinglePage makes a single authenticated GET request.
func fetchSinglePage(apiKey string, url string) ([]byte, error) {
	client := &http.Client{Timeout: 30 * time.Second}

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Authorization", fmt.Sprintf("ApiKey %s", apiKey))

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	var errEnv apiErrorEnvelope
	if err := json.Unmarshal(body, &errEnv); err == nil && errEnv.Error != nil {
		return nil, fmt.Errorf("API error: %s", errEnv.Error.Error)
	}

	return body, nil
}
