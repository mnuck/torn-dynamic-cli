package services

import (
	"context"
	"testing"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

func makeCrime(id int, scope int, paid bool, readyAt, executedAt int64) domain.Crime {
	c := domain.Crime{
		ID:      id,
		Name:    "Test Crime",
		Status:  "Successful",
		ReadyAt: time.Unix(readyAt, 0),
		Rewards: domain.CrimeRewards{
			Money:   1000,
			Respect: 5,
			Scope:   scope,
			Paid:    paid,
		},
	}
	if executedAt > 0 {
		t := time.Unix(executedAt, 0)
		c.ExecutedAt = &t
	}
	return c
}

func TestGetUnpaidOCs_FiltersScope0(t *testing.T) {
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			makeCrime(1, 0, false, 1000, 1100), // scope=0 → skip
			makeCrime(2, 2, false, 1000, 1100), // scope=2 → include
		},
	}
	svc := NewOCPayoutService(repo)
	unpaid, err := svc.GetUnpaidOCs(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(unpaid) != 1 || unpaid[0].Crime.ID != 2 {
		t.Errorf("expected only crime 2, got %+v", unpaid)
	}
}

func TestGetUnpaidOCs_FiltersAlreadyPaid(t *testing.T) {
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			makeCrime(1, 2, true, 1000, 1100),  // paid → skip
			makeCrime(2, 2, false, 1000, 1100), // unpaid → include
		},
	}
	svc := NewOCPayoutService(repo)
	unpaid, err := svc.GetUnpaidOCs(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(unpaid) != 1 || unpaid[0].Crime.ID != 2 {
		t.Errorf("expected only crime 2, got %+v", unpaid)
	}
}

func TestGetUnpaidOCs_FiltersNotYetExecuted(t *testing.T) {
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			makeCrime(1, 2, false, 1000, 0),    // no executedAt → skip
			makeCrime(2, 2, false, 1000, 1100), // executed → include
		},
	}
	svc := NewOCPayoutService(repo)
	unpaid, err := svc.GetUnpaidOCs(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(unpaid) != 1 || unpaid[0].Crime.ID != 2 {
		t.Errorf("expected only crime 2, got %+v", unpaid)
	}
}

func TestGetUnpaidOCs_ComputesDelay(t *testing.T) {
	const readyAt = int64(1000000)
	const executedAt = int64(1000000 + 45*60) // 45 minutes late

	repo := &mockFactionRepo{
		crimes: []domain.Crime{makeCrime(1, 2, false, readyAt, executedAt)},
	}
	svc := NewOCPayoutService(repo)
	unpaid, _ := svc.GetUnpaidOCs(context.Background())

	if unpaid[0].DelaySec != 45*60 {
		t.Errorf("expected 2700s delay, got %d", unpaid[0].DelaySec)
	}
	if !unpaid[0].IsLate {
		t.Error("expected IsLate=true for 45-minute delay")
	}
}

func TestGetUnpaidOCs_OnTimeVerdictUnder30Min(t *testing.T) {
	const readyAt = int64(1000000)
	const executedAt = int64(1000000 + 20*60) // 20 minutes — within threshold

	repo := &mockFactionRepo{
		crimes: []domain.Crime{makeCrime(1, 2, false, readyAt, executedAt)},
	}
	svc := NewOCPayoutService(repo)
	unpaid, _ := svc.GetUnpaidOCs(context.Background())

	if unpaid[0].IsLate {
		t.Error("expected IsLate=false for 20-minute delay")
	}
}

func TestGetUnpaidOCs_SortedOldestFirst(t *testing.T) {
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			makeCrime(1, 2, false, 1000, 2000),
			makeCrime(2, 2, false, 1000, 1500), // older
		},
	}
	svc := NewOCPayoutService(repo)
	unpaid, _ := svc.GetUnpaidOCs(context.Background())

	if unpaid[0].Crime.ID != 2 || unpaid[1].Crime.ID != 1 {
		t.Errorf("expected oldest (id=2) first, got ids %d, %d", unpaid[0].Crime.ID, unpaid[1].Crime.ID)
	}
}
