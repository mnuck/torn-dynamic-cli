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

// Helper to create a dummy spec and command for testing
func setupTestCmd(serverURL string) (*cobra.Command, *OpenAPISpec) {
	spec := &OpenAPISpec{
		Servers: []Server{{URL: serverURL}},
	}

	cmd := &cobra.Command{}
	cmd.Flags().String("key", "", "API Key")
	cmd.Flags().String("id", "", "ID")
	cmd.Flags().String("striptags", "", "Striptags")
	cmd.Flags().Bool("all", false, "All")

	return cmd, spec
}

func TestExecuteRequest_HappyPath(t *testing.T) {
	// Mock Server
	stats := map[string]interface{}{"status": "ok", "id": 123}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Assertions on request
		if r.URL.Path != "/user/123/profile" {
			t.Errorf("Expected path /user/123/profile, got %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "ApiKey mykey" {
			t.Errorf("Missing or wrong Auth header: %s", r.Header.Get("Authorization"))
		}

		json.NewEncoder(w).Encode(stats)
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().Set("key", "mykey")
	cmd.Flags().Set("id", "123")

	op := &Operation{}
	pathParams := []string{"id"}

	// Test
	err := ExecuteRequest(cmd, spec, "/user/{id}/profile", op, pathParams)
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}
}

func TestExecuteRequest_APIError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte(`{"error": "Incorrect key"}`))
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().Set("key", "badkey")

	err := ExecuteRequest(cmd, spec, "/user/profile", &Operation{}, []string{})

	// We expect an error because status >= 400
	if err == nil {
		t.Error("Expected error for 403 Forbidden, got nil")
	}
}

func TestExecuteRequest_MalformedJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{not valid json`))
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().Set("key", "testkey")

	// Should NOT error, but print raw body.
	// ExecuteRequest currently returns nil if read succeeds, even if JSON unmarshal fails.
	// This is "by design" for the CLI (just dump output).
	err := ExecuteRequest(cmd, spec, "/user/profile", &Operation{}, []string{})
	if err != nil {
		t.Errorf("Did not expect error for malformed JSON, just raw print: %v", err)
	}
}

func TestExecuteRequest_TornLogic_ErrorIn200(t *testing.T) {
	// Torn sometimes returns 200 OK but with {"error": ...}
	// The CLI should just print it. usage is valid.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"error": {"code": 2, "error": "Incorrect key"}}`))
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().Set("key", "testkey")
	err := ExecuteRequest(cmd, spec, "/user/profile", &Operation{}, []string{})
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}
}

func TestExecuteRequest_EmptyPathParam(t *testing.T) {
	// Edge case: User omits ID for /user/{id}/profile
	// Logic: should strip it and request /user/profile
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/user/profile" {
			t.Errorf("Expected path /user/profile (stripped id), got %s", r.URL.Path)
		}
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().Set("key", "testkey")
	// ID not set

	err := ExecuteRequest(cmd, spec, "/user/{id}/profile", &Operation{}, []string{"id"})
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}
}

func TestExecuteRequest_NoKeyReturnsError(t *testing.T) {
	os.Unsetenv("TORN_API_KEY")
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("server should not be called when no key is provided")
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	// no key flag set, no env var

	err := ExecuteRequest(cmd, spec, "/user/profile", &Operation{}, []string{})
	if err == nil {
		t.Error("expected error when no API key is provided, got nil")
	}
}

func TestExecuteRequest_QueryParamPassthrough(t *testing.T) {
	// Flags that are Changed should appear in the query string.
	// Path params, "key", and "help" should be excluded.
	var gotQuery string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		w.Write([]byte(`{}`))
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().String("limit", "", "Limit")
	cmd.Flags().String("sort", "", "Sort")
	cmd.Flags().Set("key", "testkey")
	cmd.Flags().Set("limit", "10") // Changed=true; should appear
	// sort not set — should not appear
	// key changed but must be excluded

	err := ExecuteRequest(cmd, spec, "/user/profile", &Operation{}, []string{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotQuery != "limit=10" {
		t.Errorf("expected query 'limit=10', got '%s'", gotQuery)
	}
}

func TestExecuteRequest_AllFlag_MultiPage(t *testing.T) {
	// --all should follow _metadata.links.next and accumulate array items.
	callCount := 0
	var ts *httptest.Server
	ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		if callCount == 1 {
			body := fmt.Sprintf(`{"attacks":[{"id":1}],"_metadata":{"links":{"next":"%s/p2"}}}`, ts.URL)
			w.Write([]byte(body))
		} else {
			w.Write([]byte(`{"attacks":[{"id":2}],"_metadata":{}}`))
		}
	}))
	defer ts.Close()

	cmd, spec := setupTestCmd(ts.URL)
	cmd.Flags().Set("key", "testkey")
	cmd.Flags().Set("all", "true")

	err := ExecuteRequest(cmd, spec, "/faction/attacks", &Operation{}, []string{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if callCount != 2 {
		t.Errorf("expected 2 HTTP calls for pagination, made %d", callCount)
	}
}
