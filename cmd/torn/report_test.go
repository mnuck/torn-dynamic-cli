package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/spf13/cobra"
)

// ---- getAPIKey ----

func TestGetAPIKey_FromFlag(t *testing.T) {
	cmd := &cobra.Command{}
	cmd.Flags().String("key", "", "API Key")
	cmd.Flags().Set("key", "flagkey")

	key, err := getAPIKey(cmd)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if key != "flagkey" {
		t.Errorf("expected 'flagkey', got '%s'", key)
	}
}

func TestGetAPIKey_FallsBackToEnv(t *testing.T) {
	os.Setenv("TORN_API_KEY", "envkey")
	defer os.Unsetenv("TORN_API_KEY")

	cmd := &cobra.Command{}
	cmd.Flags().String("key", "", "API Key")
	// flag left empty

	key, err := getAPIKey(cmd)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if key != "envkey" {
		t.Errorf("expected 'envkey', got '%s'", key)
	}
}

func TestGetAPIKey_FlagTakesPrecedenceOverEnv(t *testing.T) {
	os.Setenv("TORN_API_KEY", "envkey")
	defer os.Unsetenv("TORN_API_KEY")

	cmd := &cobra.Command{}
	cmd.Flags().String("key", "", "API Key")
	cmd.Flags().Set("key", "flagkey")

	key, err := getAPIKey(cmd)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if key != "flagkey" {
		t.Errorf("flag should win over env: expected 'flagkey', got '%s'", key)
	}
}

func TestGetAPIKey_MissingReturnsError(t *testing.T) {
	os.Unsetenv("TORN_API_KEY")

	cmd := &cobra.Command{}
	cmd.Flags().String("key", "", "API Key")

	_, err := getAPIKey(cmd)
	if err == nil {
		t.Error("expected error when no key is provided, got nil")
	}
}

// ---- fetchAllPages ----

// buildPageResponse creates a JSON body that looks like a Torn paginated response.
// nextURL is the value to put in _metadata.links.next (empty string omits it).
func buildPageResponse(t *testing.T, data map[string]interface{}, nextURL string) []byte {
	t.Helper()
	body := map[string]interface{}{"data": data}
	if nextURL != "" {
		body["_metadata"] = map[string]interface{}{
			"links": map[string]interface{}{"next": nextURL},
		}
	}
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("failed to marshal test response: %v", err)
	}
	return b
}

func TestFetchAllPages_SinglePage(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "ApiKey testkey" {
			t.Errorf("wrong auth header: %s", r.Header.Get("Authorization"))
		}
		w.Write(buildPageResponse(t, map[string]interface{}{"foo": "bar"}, ""))
	}))
	defer ts.Close()

	pages, err := fetchAllPages("testkey", ts.URL+"/faction/members")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(pages) != 1 {
		t.Errorf("expected 1 page, got %d", len(pages))
	}
}

func TestFetchAllPages_MultiPage(t *testing.T) {
	callCount := 0
	var ts *httptest.Server
	ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		if callCount == 1 {
			// First page: point to second page
			w.Write(buildPageResponse(t, map[string]interface{}{"page": 1}, ts.URL+"/page2"))
		} else {
			// Second page: no next link
			w.Write(buildPageResponse(t, map[string]interface{}{"page": 2}, ""))
		}
	}))
	defer ts.Close()

	pages, err := fetchAllPages("testkey", ts.URL+"/page1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(pages) != 2 {
		t.Errorf("expected 2 pages, got %d", len(pages))
	}
	if callCount != 2 {
		t.Errorf("expected 2 HTTP calls, made %d", callCount)
	}
}

func TestFetchAllPages_PrevLinkFallback(t *testing.T) {
	// Some Torn endpoints paginate backwards via "prev" instead of "next"
	callCount := 0
	var ts *httptest.Server
	ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		body := map[string]interface{}{"page": callCount}
		if callCount == 1 {
			body["_metadata"] = map[string]interface{}{
				"links": map[string]interface{}{"prev": fmt.Sprintf("%s/page2", ts.URL)},
			}
		}
		b, _ := json.Marshal(body)
		w.Write(b)
	}))
	defer ts.Close()

	pages, err := fetchAllPages("testkey", ts.URL+"/page1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(pages) != 2 {
		t.Errorf("expected 2 pages via prev link, got %d", len(pages))
	}
}

func TestFetchAllPages_HTTP4xx(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		w.Write([]byte(`{"error":"bad key"}`))
	}))
	defer ts.Close()

	_, err := fetchAllPages("badkey", ts.URL+"/faction/members")
	if err == nil {
		t.Error("expected error for HTTP 401, got nil")
	}
}

func TestFetchAllPages_TornErrorIn200(t *testing.T) {
	// Torn sometimes returns 200 OK with an error body
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"error":{"code":2,"error":"Incorrect key"}}`))
	}))
	defer ts.Close()

	_, err := fetchAllPages("badkey", ts.URL+"/faction/members")
	if err == nil {
		t.Error("expected error for Torn error-in-200 body, got nil")
	}
}
