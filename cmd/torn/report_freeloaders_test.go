package main

import (
	"testing"
)

func TestClassifyFreeloaders_IsFreeloader(t *testing.T) {
	xanaxUsage := map[string]int{"Alice": 3}
	nameToID := map[string]int{"Alice": 1}
	memberData := map[int]memberInfo{
		1: {ID: 1, Name: "Alice", Level: 10, Position: "Member", DaysInFaction: 30, IsInOC: false},
	}
	ocParticipants := map[int]bool{}

	freeloaders, compliant := classifyFreeloaders(xanaxUsage, nameToID, memberData, ocParticipants)

	if len(freeloaders) != 1 {
		t.Fatalf("expected 1 freeloader, got %d", len(freeloaders))
	}
	if freeloaders[0].Name != "Alice" {
		t.Errorf("expected Alice, got %s", freeloaders[0].Name)
	}
	if freeloaders[0].XanaxCount != 3 {
		t.Errorf("expected XanaxCount=3, got %d", freeloaders[0].XanaxCount)
	}
	if compliant != 0 {
		t.Errorf("expected 0 compliant, got %d", compliant)
	}
}

func TestClassifyFreeloaders_CompliantViaOCParticipants(t *testing.T) {
	xanaxUsage := map[string]int{"Bob": 2}
	nameToID := map[string]int{"Bob": 2}
	memberData := map[int]memberInfo{
		2: {ID: 2, Name: "Bob", IsInOC: false},
	}
	ocParticipants := map[int]bool{2: true}

	freeloaders, compliant := classifyFreeloaders(xanaxUsage, nameToID, memberData, ocParticipants)

	if len(freeloaders) != 0 {
		t.Errorf("expected 0 freeloaders, got %d", len(freeloaders))
	}
	if compliant != 1 {
		t.Errorf("expected 1 compliant, got %d", compliant)
	}
}

func TestClassifyFreeloaders_CompliantViaIsInOC(t *testing.T) {
	// Member is flagged IsInOC=true on their member record (currently in an active OC slot)
	xanaxUsage := map[string]int{"Carol": 1}
	nameToID := map[string]int{"Carol": 3}
	memberData := map[int]memberInfo{
		3: {ID: 3, Name: "Carol", IsInOC: true},
	}
	ocParticipants := map[int]bool{}

	freeloaders, compliant := classifyFreeloaders(xanaxUsage, nameToID, memberData, ocParticipants)

	if len(freeloaders) != 0 {
		t.Errorf("expected 0 freeloaders, got %d", len(freeloaders))
	}
	if compliant != 1 {
		t.Errorf("expected 1 compliant, got %d", compliant)
	}
}

func TestClassifyFreeloaders_IgnoresFormerMembers(t *testing.T) {
	// Username appears in xanaxUsage but not in nameToID — left the faction
	xanaxUsage := map[string]int{"Ghost": 5}
	nameToID := map[string]int{}
	memberData := map[int]memberInfo{}
	ocParticipants := map[int]bool{}

	freeloaders, compliant := classifyFreeloaders(xanaxUsage, nameToID, memberData, ocParticipants)

	if len(freeloaders) != 0 {
		t.Errorf("expected 0 freeloaders (former member ignored), got %d", len(freeloaders))
	}
	if compliant != 0 {
		t.Errorf("expected 0 compliant, got %d", compliant)
	}
}

func TestClassifyFreeloaders_MixedResult(t *testing.T) {
	xanaxUsage := map[string]int{"Alice": 3, "Bob": 2, "Carol": 1}
	nameToID := map[string]int{"Alice": 1, "Bob": 2, "Carol": 3}
	memberData := map[int]memberInfo{
		1: {ID: 1, Name: "Alice", IsInOC: false},
		2: {ID: 2, Name: "Bob", IsInOC: true},
		3: {ID: 3, Name: "Carol", IsInOC: false},
	}
	ocParticipants := map[int]bool{3: true}

	freeloaders, compliant := classifyFreeloaders(xanaxUsage, nameToID, memberData, ocParticipants)

	if len(freeloaders) != 1 {
		t.Fatalf("expected 1 freeloader, got %d", len(freeloaders))
	}
	if freeloaders[0].Name != "Alice" {
		t.Errorf("expected Alice as freeloader, got %s", freeloaders[0].Name)
	}
	if compliant != 2 {
		t.Errorf("expected 2 compliant, got %d", compliant)
	}
}
