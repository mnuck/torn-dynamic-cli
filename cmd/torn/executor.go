package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
	"github.com/tidwall/gjson"
)

func ExecuteRequest(cmd *cobra.Command, spec *OpenAPISpec, rawPath string, op *Operation, pathParams []string) error {
	// 1. Construct URL
	// Replace path params
	finalPath := rawPath
	for _, pp := range pathParams {
		val, err := cmd.Flags().GetString(pp)
		if err != nil {
			return err
		}
		if val == "" {
			// For optional path params or implicit "me", we might leave placeholders?
			// But usually {id} is required if present in path.
			// If the user didn't supply it, and the path has {id}, we can't build a valid URL unless we switch to an alternative path (e.g. /user).
			// However, our current architecture maps a specific spec path to this closure.
			// If the user meant "myself" (no ID), they might have used `torn user profile` without --id.
			// If the path was `/user/{id}/profile`, then `finalPath` has `{id}`.
			// If we remove `{id}` segments during path construction, we might end up with `//` or invalid paths.
			// Torn API specific: /user/ == /user/{my_id}/
			// So if `id` is missing, we could try to strip it?
			// e.g. /user/{id}/profile -> /user/profile ?
			// Let's try flexible replacement: if empty, remove the preceding slash and the param?
			// Or just replace with empty string and hope `//` is handled? -> `api.torn.com/v2/user//profile` might fail.
			// Let's just strip `{id}`.

			finalPath = strings.ReplaceAll(finalPath, "/{"+pp+"}", "")
			finalPath = strings.ReplaceAll(finalPath, "{"+pp+"}", "") // Fallback
		} else {
			finalPath = strings.ReplaceAll(finalPath, "{"+pp+"}", val)
		}
	}

	// 2. Construct Query Params
	queryParams := url.Values{}

	// We need to visit all flags that were SET by the user or have defaults.
	// Spec flags.
	cmd.Flags().VisitAll(func(flag *pflag.Flag) {
		// Skip hidden/system flags if any.
		// Skip path params and "key" global flag
		isPath := false
		for _, pp := range pathParams {
			if pp == flag.Name {
				isPath = true
				break
			}
		}
		if flag.Name == "key" {
			isPath = true
		}
		if flag.Name == "help" {
			isPath = true
		}

		if !isPath {
			// Only add if explicitly changed or if it has a default?
			// OpenAPI defaults are tricky. For now, strictly what user provided.
			if flag.Changed {
				queryParams.Add(flag.Name, flag.Value.String())
			}
		}
	})

	// Base URL
	baseURL := "https://api.torn.com/v2"
	if len(spec.Servers) > 0 {
		baseURL = spec.Servers[0].URL
	}

	// Handle query string
	q := queryParams.Encode()
	fullURL := fmt.Sprintf("%s%s", baseURL, finalPath)
	if q != "" {
		fullURL += "?" + q
	}

	// 3. Auth
	apiKey, err := getAPIKey(cmd)
	if err != nil {
		return err
	}

	// 5. Execute Loop
	client := &http.Client{}

	// Check for --all flag
	fetchAll, _ := cmd.Flags().GetBool("all")

	// Initial fetch
	nextURL := fullURL

	// When fetching all pages, accumulate and merge array fields into one response.
	var mergedArrayKey string
	var mergedItems []json.RawMessage
	var lastPage map[string]json.RawMessage

	for {
		req, err := http.NewRequest("GET", nextURL, nil)
		if err != nil {
			return fmt.Errorf("failed to create request: %w", err)
		}

		// Pass headers
		if apiKey != "" {
			req.Header.Set("Authorization", "ApiKey "+apiKey)
		}

		resp, err := client.Do(req)
		if err != nil {
			return fmt.Errorf("request failed: %w", err)
		}

		// Read body
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close() // Close immediately
		if err != nil {
			return fmt.Errorf("failed to read body: %w", err)
		}

		if resp.StatusCode >= 400 {
			fmt.Println(string(body))
			return fmt.Errorf("api returned error status: %d", resp.StatusCode)
		}

		if !fetchAll {
			// Single page: print and exit.
			var jsonObj interface{}
			var printErr error
			if err := json.Unmarshal(body, &jsonObj); err == nil {
				pretty, _ := json.MarshalIndent(jsonObj, "", "  ")
				_, printErr = fmt.Println(string(pretty))
			} else {
				_, printErr = fmt.Println(string(body))
			}
			if printErr != nil {
				return nil // broken pipe
			}
			break
		}

		// Multi-page: parse into raw fields and accumulate.
		var page map[string]json.RawMessage
		if err := json.Unmarshal(body, &page); err != nil {
			// Not JSON — print as-is and stop.
			fmt.Println(string(body))
			break
		}
		lastPage = page

		// Find the first array field (not _metadata) and accumulate it.
		for k, v := range page {
			if k == "_metadata" {
				continue
			}
			// Check if this value is a JSON array.
			trimmed := strings.TrimSpace(string(v))
			if len(trimmed) > 0 && trimmed[0] == '[' {
				if mergedArrayKey == "" {
					mergedArrayKey = k
				}
				if k == mergedArrayKey {
					var items []json.RawMessage
					if err := json.Unmarshal(v, &items); err == nil {
						mergedItems = append(mergedItems, items...)
					}
				}
				break
			}
		}

		// Determine next page URL.
		nextLink := gjson.GetBytes(body, "_metadata.links.next").String()
		if nextLink == "" {
			nextLink = gjson.GetBytes(body, "_metadata.next").String()
		}
		if nextLink == "" {
			// Fallback to _metadata.links.prev (Events pagination)
			nextLink = gjson.GetBytes(body, "_metadata.links.prev").String()
		}

		if nextLink == "" {
			// No more pages — build and print merged response.
			if lastPage != nil && mergedArrayKey != "" {
				merged := make(map[string]json.RawMessage)
				for k, v := range lastPage {
					merged[k] = v
				}
				arrBytes, _ := json.Marshal(mergedItems)
				merged[mergedArrayKey] = arrBytes
				pretty, _ := json.MarshalIndent(merged, "", "  ")
				if _, err := fmt.Println(string(pretty)); err != nil {
					return nil // broken pipe
				}
			} else if lastPage != nil {
				pretty, _ := json.MarshalIndent(lastPage, "", "  ")
				if _, err := fmt.Println(string(pretty)); err != nil {
					return nil // broken pipe
				}
			}
			break
		}

		nextURL = nextLink
	}

	return nil
}
