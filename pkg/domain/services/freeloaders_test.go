package services

import (
	"context"
	"testing"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

func TestIdentifyFreeloaders_UsedXanaxNotInOC(t *testing.T) {
	repo := &mockFactionRepo{
		members: []domain.Member{
			{ID: 1, Name: "Alice", Level: 10, Position: "Member", DaysInFaction: 30},
			{ID: 2, Name: "Bob", Level: 15, Position: "Member", DaysInFaction: 60},
		},
		news: []domain.XanaxUsage{
			{Username: "Alice", Count: 1},
			{Username: "Alice", Count: 1},
			{Username: "Bob", Count: 1},
		},
		// Bob is in an active crime; Alice is in none
		active: []domain.Crime{
			{ID: 100, Slots: []domain.CrimeSlot{{User: &domain.User{ID: 2}}}},
		},
	}
	svc := NewFreeloaderService(repo)

	freeloaders, compliant, err := svc.IdentifyFreeloaders(context.Background(), 48)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(freeloaders) != 1 {
		t.Fatalf("expected 1 freeloader, got %d", len(freeloaders))
	}
	if freeloaders[0].Name != "Alice" {
		t.Errorf("expected Alice flagged, got %s", freeloaders[0].Name)
	}
	if freeloaders[0].XanaxCount != 2 {
		t.Errorf("expected Alice xanax count 2, got %d", freeloaders[0].XanaxCount)
	}
	if compliant != 1 {
		t.Errorf("expected 1 compliant member, got %d", compliant)
	}
}

func TestIdentifyFreeloaders_CompletedCrimeCounts(t *testing.T) {
	repo := &mockFactionRepo{
		members: []domain.Member{
			{ID: 1, Name: "Alice", Position: "Member"},
		},
		news: []domain.XanaxUsage{{Username: "Alice", Count: 1}},
		// Alice participated in a recently completed crime → compliant
		crimes: []domain.Crime{
			{ID: 200, Slots: []domain.CrimeSlot{{User: &domain.User{ID: 1}}}},
		},
	}
	svc := NewFreeloaderService(repo)

	freeloaders, compliant, err := svc.IdentifyFreeloaders(context.Background(), 48)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(freeloaders) != 0 {
		t.Errorf("expected 0 freeloaders (Alice in completed OC), got %d", len(freeloaders))
	}
	if compliant != 1 {
		t.Errorf("expected 1 compliant, got %d", compliant)
	}
}

func TestIdentifyFreeloaders_UnknownUserSkipped(t *testing.T) {
	repo := &mockFactionRepo{
		members: []domain.Member{{ID: 1, Name: "Alice", Position: "Member"}},
		// "Ghost" used xanax but isn't in the member list (left faction)
		news: []domain.XanaxUsage{{Username: "Ghost", Count: 5}},
	}
	svc := NewFreeloaderService(repo)

	freeloaders, _, err := svc.IdentifyFreeloaders(context.Background(), 48)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(freeloaders) != 0 {
		t.Errorf("expected non-member Ghost skipped, got %d freeloaders", len(freeloaders))
	}
}

func TestIdentifyFreeloaders_NoXanaxNoFreeloaders(t *testing.T) {
	repo := &mockFactionRepo{
		members: []domain.Member{{ID: 1, Name: "Alice", Position: "Member"}},
	}
	svc := NewFreeloaderService(repo)

	freeloaders, compliant, err := svc.IdentifyFreeloaders(context.Background(), 48)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(freeloaders) != 0 || compliant != 0 {
		t.Errorf("expected no results, got %d freeloaders, %d compliant", len(freeloaders), compliant)
	}
}
