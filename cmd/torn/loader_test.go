package main

import (
	"testing"
)

func TestLoadSpec_ValidJSON(t *testing.T) {
	data := []byte(`{
		"servers": [{"url": "https://api.torn.com"}],
		"paths": {
			"/user/{id}/profile": {
				"get": {
					"summary": "Get user profile",
					"operationId": "getUserProfile",
					"parameters": []
				}
			}
		},
		"components": {"parameters": {}}
	}`)

	spec, err := LoadSpec(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(spec.Servers) != 1 {
		t.Errorf("expected 1 server, got %d", len(spec.Servers))
	}
	if spec.Servers[0].URL != "https://api.torn.com" {
		t.Errorf("expected server URL 'https://api.torn.com', got '%s'", spec.Servers[0].URL)
	}
	if _, ok := spec.Paths["/user/{id}/profile"]; !ok {
		t.Error("expected path '/user/{id}/profile' to exist in spec")
	}
}

func TestLoadSpec_MalformedJSON(t *testing.T) {
	_, err := LoadSpec([]byte(`{not valid json`))
	if err == nil {
		t.Error("expected error for malformed JSON, got nil")
	}
}

func TestLoadSpec_EmptySpec(t *testing.T) {
	spec, err := LoadSpec([]byte(`{}`))
	if err != nil {
		t.Fatalf("unexpected error for empty spec: %v", err)
	}
	if len(spec.Paths) != 0 {
		t.Errorf("expected 0 paths, got %d", len(spec.Paths))
	}
	if len(spec.Servers) != 0 {
		t.Errorf("expected 0 servers, got %d", len(spec.Servers))
	}
}

func TestLoadSpec_OperationSummaryParsed(t *testing.T) {
	data := []byte(`{
		"servers": [],
		"paths": {
			"/faction/members": {
				"get": {
					"summary": "Get faction members",
					"operationId": "getFactionMembers",
					"parameters": []
				}
			}
		},
		"components": {"parameters": {}}
	}`)

	spec, err := LoadSpec(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	path, ok := spec.Paths["/faction/members"]
	if !ok {
		t.Fatal("expected '/faction/members' path")
	}
	if path.Get == nil {
		t.Fatal("expected GET operation on '/faction/members'")
	}
	if path.Get.Summary != "Get faction members" {
		t.Errorf("expected summary 'Get faction members', got '%s'", path.Get.Summary)
	}
	if path.Get.OperationID != "getFactionMembers" {
		t.Errorf("expected operationId 'getFactionMembers', got '%s'", path.Get.OperationID)
	}
}
