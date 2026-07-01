package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
	"github.com/spf13/cobra"
)

// NewReportCmd returns a parent "report" command with subcommands attached.
func NewReportCmd(freeloaderService *services.FreeloaderService, hitService *services.HitService, goodThugService *services.GoodThugService) *cobra.Command {
	reportCmd := &cobra.Command{
		Use:   "report",
		Short: "Generate faction reports",
		Long:  "Commands for generating analytical reports about faction activity",
	}

	reportCmd.AddCommand(newFreeloadersCmd(freeloaderService))
	reportCmd.AddCommand(newGoodThugsCmd(goodThugService))
	reportCmd.AddCommand(newHitsCmd(hitService))
	reportCmd.AddCommand(newLateOCsCmd())
	reportCmd.AddCommand(newOCPayoutsCmd())
	reportCmd.AddCommand(newCompanyStatusCmd())
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
		var errEnv apiErrorEnvelope
		if err := json.Unmarshal(body, &errEnv); err == nil && errEnv.Error != nil {
			return nil, fmt.Errorf("API error: %s", errEnv.Error.Error)
		}

		pages = append(pages, body)

		// Follow next page link; fall back to prev for endpoints that paginate backwards.
		nextURL = ""
		var meta apiPageMeta
		if err := json.Unmarshal(body, &meta); err == nil && meta.Metadata != nil {
			if meta.Metadata.Links != nil {
				nextURL = meta.Metadata.Links.Next
			}
			if nextURL == "" {
				nextURL = meta.Metadata.Next
			}
			if nextURL == "" && meta.Metadata.Links != nil {
				nextURL = meta.Metadata.Links.Prev
			}
		}

		// No sleep needed: Torn allows 100 req/min and natural HTTP latency
		// keeps us well within that limit.
	}

	return pages, nil
}
