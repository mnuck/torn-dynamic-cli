package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
	// ID not set

	err := ExecuteRequest(cmd, spec, "/user/{id}/profile", &Operation{}, []string{"id"})
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}
}
