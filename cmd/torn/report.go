package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/spf13/cobra"
	"github.com/tidwall/gjson"
)

// NewReportCmd returns a parent "report" command with subcommands attached.
func NewReportCmd() *cobra.Command {
	reportCmd := &cobra.Command{
		Use:   "report",
		Short: "Generate faction reports",
		Long:  "Commands for generating analytical reports about faction activity",
	}

	reportCmd.AddCommand(newFreeloadersCmd())
	reportCmd.AddCommand(newGoodThugsCmd())
	reportCmd.AddCommand(newHitsCmd())
	reportCmd.AddCommand(newLateOCsCmd())
	return reportCmd
}

// getAPIKey retrieves the API key from the --key flag or TORN_API_KEY env var.
func getAPIKey(cmd *cobra.Command) (string, error) {
	key, _ := cmd.Flags().GetString("key")
	if key == "" {
		key = os.Getenv("TORN_API_KEY")
	}
	if key == "" {
		return "", fmt.Errorf("API key required via --key flag or TORN_API_KEY environment variable")
	}
	return key, nil
}

// memberInfo holds parsed data for a single faction member.
type memberInfo struct {
	ID            int
	Name          string
	Level         int
	Position      string
	DaysInFaction int
	IsInOC        bool
}

// fetchAllPages follows pagination links to retrieve all pages of a resource.
// Returns a slice of response bodies (one per page).
func fetchAllPages(apiKey string, startURL string) ([][]byte, error) {
	var pages [][]byte
	nextURL := startURL

	client := &http.Client{Timeout: 30 * time.Second}

	for nextURL != "" {
		req, err := http.NewRequest("GET", nextURL, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Authorization", fmt.Sprintf("ApiKey %s", apiKey))

		resp, err := client.Do(req)
		if err != nil {
			return nil, fmt.Errorf("request failed: %w", err)
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()

		if err != nil {
			return nil, fmt.Errorf("failed to read response: %w", err)
		}

		if resp.StatusCode >= 400 {
			return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
		}

		// Torn API sometimes returns 200 with an error body
		if gjson.GetBytes(body, "error").Exists() {
			return nil, fmt.Errorf("API error: %s", gjson.GetBytes(body, "error.error").String())
		}

		pages = append(pages, body)

		// Follow next page link; fall back to prev for endpoints that paginate backwards.
		nextURL = gjson.GetBytes(body, "_metadata.links.next").String()
		if nextURL == "" {
			nextURL = gjson.GetBytes(body, "_metadata.links.prev").String()
		}

		// No sleep needed: Torn allows 100 req/min and natural HTTP latency
		// keeps us well within that limit.
	}

	return pages, nil
}
