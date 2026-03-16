package main

import (
	"encoding/json"
	"testing"
)

func makeAttackPage(t *testing.T, attacks []map[string]interface{}) []byte {
	t.Helper()
	b, err := json.Marshal(map[string]interface{}{"attacks": attacks})
	if err != nil {
		t.Fatalf("failed to marshal attack page: %v", err)
	}
	return b
}

func TestFilterHits_MatchesByName(t *testing.T) {
	page := makeAttackPage(t, []map[string]interface{}{
		{"attacker": map[string]interface{}{"name": "Alice"}, "defender": map[string]interface{}{"name": "Enemy1"}, "ended": 1700000000, "result": "Attacked", "respect_gain": 1.5, "code": "abc123"},
		{"attacker": map[string]interface{}{"name": "Bob"}, "defender": map[string]interface{}{"name": "Enemy2"}, "ended": 1700000001, "result": "Attacked", "respect_gain": 2.0, "code": "def456"},
	})

	hits := filterHits([][]byte{page}, "Alice")

	if len(hits) != 1 {
		t.Fatalf("expected 1 hit for Alice, got %d", len(hits))
	}
	if hits[0].Defender != "Enemy1" {
		t.Errorf("expected defender Enemy1, got %s", hits[0].Defender)
	}
	if hits[0].Respect != 1.5 {
		t.Errorf("expected respect 1.5, got %f", hits[0].Respect)
	}
}

func TestFilterHits_BuildsLinkFromCode(t *testing.T) {
	page := makeAttackPage(t, []map[string]interface{}{
		{"attacker": map[string]interface{}{"name": "Alice"}, "defender": map[string]interface{}{"name": "Enemy"}, "ended": 1700000000, "result": "Attacked", "respect_gain": 1.0, "code": "abc123"},
	})

	hits := filterHits([][]byte{page}, "Alice")

	expected := "https://www.torn.com/loader.php?sid=attackLog&ID=abc123"
	if hits[0].Link != expected {
		t.Errorf("expected link %s, got %s", expected, hits[0].Link)
	}
}

func TestFilterHits_EmptyLinkWhenNoCode(t *testing.T) {
	page := makeAttackPage(t, []map[string]interface{}{
		{"attacker": map[string]interface{}{"name": "Alice"}, "defender": map[string]interface{}{"name": "Enemy"}, "ended": 1700000000, "result": "Attacked", "respect_gain": 0.0, "code": ""},
	})

	hits := filterHits([][]byte{page}, "Alice")

	if hits[0].Link != "" {
		t.Errorf("expected empty link when code is missing, got %s", hits[0].Link)
	}
}

func TestFilterHits_MultiplePages(t *testing.T) {
	page1 := makeAttackPage(t, []map[string]interface{}{
		{"attacker": map[string]interface{}{"name": "Alice"}, "defender": map[string]interface{}{"name": "E1"}, "ended": 1700000001, "result": "Attacked", "respect_gain": 1.0, "code": "c1"},
	})
	page2 := makeAttackPage(t, []map[string]interface{}{
		{"attacker": map[string]interface{}{"name": "Alice"}, "defender": map[string]interface{}{"name": "E2"}, "ended": 1700000002, "result": "Mugged", "respect_gain": 2.0, "code": "c2"},
	})

	hits := filterHits([][]byte{page1, page2}, "Alice")

	if len(hits) != 2 {
		t.Errorf("expected 2 hits across 2 pages, got %d", len(hits))
	}
}

func TestFilterHits_NoMatches(t *testing.T) {
	page := makeAttackPage(t, []map[string]interface{}{
		{"attacker": map[string]interface{}{"name": "Bob"}, "defender": map[string]interface{}{"name": "Enemy"}, "ended": 1700000000, "result": "Attacked", "respect_gain": 1.0, "code": "abc"},
	})

	hits := filterHits([][]byte{page}, "Alice")

	if len(hits) != 0 {
		t.Errorf("expected 0 hits when name doesn't match, got %d", len(hits))
	}
}

func TestFilterHits_EmptyPages(t *testing.T) {
	hits := filterHits(nil, "Alice")
	if len(hits) != 0 {
		t.Errorf("expected 0 hits for empty pages, got %d", len(hits))
	}
}
