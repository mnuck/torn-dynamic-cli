package main

import (
	"fmt"
	"os"
	"sort"
	"time"

	"github.com/spf13/cobra"
	"github.com/tidwall/gjson"
)

func newHitsCmd() *cobra.Command {
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
			apiKey, err := getAPIKey(cmd)
			if err != nil {
				return err
			}
			return runHitsReport(apiKey, name, days)
		},
	}

	cmd.Flags().StringVar(&name, "name", "", "Faction member's in-game name (required)")
	cmd.Flags().IntVar(&days, "days", 7, "Lookback window in days")
	return cmd
}

type hitRecord struct {
	Timestamp int64
	DateTime  string
	Result    string
	Defender  string
	Respect   float64
	Link      string
}

func runHitsReport(apiKey, name string, days int) error {
	from := time.Now().Unix() - int64(days)*86400

	fmt.Fprintf(os.Stderr, "Fetching outgoing attacks since %s...\n",
		time.Unix(from, 0).UTC().Format("2006-01-02 15:04 UTC"))

	url := fmt.Sprintf("https://api.torn.com/v2/faction/attacks?filters=out&from=%d", from)
	pages, err := fetchAllPages(apiKey, url)
	if err != nil {
		return fmt.Errorf("failed to fetch attacks: %w", err)
	}

	var hits []hitRecord
	for _, page := range pages {
		attacks := gjson.GetBytes(page, "attacks").Array()
		for _, a := range attacks {
			if a.Get("attacker.name").String() != name {
				continue
			}
			ts := a.Get("ended").Int()
			code := a.Get("code").String()
			link := ""
			if code != "" {
				link = fmt.Sprintf("https://www.torn.com/loader.php?sid=attackLog&ID=%s", code)
			}
			hits = append(hits, hitRecord{
				Timestamp: ts,
				DateTime:  time.Unix(ts, 0).UTC().Format("2006-01-02 15:04 UTC"),
				Result:    a.Get("result").String(),
				Defender:  a.Get("defender.name").String(),
				Respect:   a.Get("respect_gain").Float(),
				Link:      link,
			})
		}
	}

	sort.Slice(hits, func(i, j int) bool {
		return hits[i].Timestamp < hits[j].Timestamp
	})

	fmt.Printf("\nHITS for %s — last %d days (%d total)\n", name, days, len(hits))
	fmt.Println("--------------------------------------------------------------------------------------------")
	fmt.Printf("%-19s  %-12s  %-22s  %6s  %s\n", "Time (UTC)", "Result", "Defender", "Resp", "Link")
	fmt.Println("--------------------------------------------------------------------------------------------")

	for _, h := range hits {
		respStr := fmt.Sprintf("%+.2f", h.Respect)
		if h.Respect == 0 {
			respStr = "  0.00"
		}
		linkStr := h.Link
		if linkStr == "" {
			linkStr = "-"
		}
		fmt.Printf("%-19s  %-12s  %-22s  %6s  %s\n",
			h.DateTime, h.Result, h.Defender, respStr, linkStr)
	}

	fmt.Println()
	fmt.Printf("%d hits for %s in the last %d days\n", len(hits), name, days)
	return nil
}
