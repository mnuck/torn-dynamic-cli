package services

import (
	"context"
	"testing"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// stubClient is a TornClient whose GetUser returns configured users.
type stubClient struct {
	users map[int]*domain.User
}

func (s *stubClient) GetCrime(ctx context.Context, id int) (*domain.Crime, error) { return nil, nil }
func (s *stubClient) GetUser(ctx context.Context, id int) (*domain.User, error) {
	if u, ok := s.users[id]; ok {
		return u, nil
	}
	return &domain.User{ID: id}, nil
}
func (s *stubClient) GetMembers(ctx context.Context) ([]domain.Member, error) { return nil, nil }
func (s *stubClient) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	return nil, nil
}
func (s *stubClient) GetCrimes(ctx context.Context, category string, from *time.Time) ([]domain.Crime, error) {
	return nil, nil
}
func (s *stubClient) GetAttacks(ctx context.Context, from time.Time) ([]domain.Hit, error) {
	return nil, nil
}

var fixedNow = time.Unix(2000000, 0)

func newLateOCServiceWithClock(repo *mockFactionRepo, client *stubClient) *LateOCService {
	svc := NewLateOCService(repo, client)
	svc.now = func() time.Time { return fixedNow }
	return svc
}

func readyBool(b bool) *bool { return &b }

func TestFindLateOCs_CurrentlyLate(t *testing.T) {
	readyAt := fixedNow.Add(-30 * time.Minute) // 30 min ago, not executed
	repo := &mockFactionRepo{
		planning: []domain.Crime{
			{
				ID: 1, Name: "Cash Grab", Status: "Planning", ReadyAt: readyAt,
				Slots: []domain.CrimeSlot{
					{Label: "Picklock", User: &domain.User{ID: 10}, ItemAvailable: readyBool(true)},
					{Label: "Lookout", User: &domain.User{ID: 20}},
				},
			},
		},
	}
	client := &stubClient{users: map[int]*domain.User{
		10: {ID: 10, Name: "Alice", Status: domain.UserStatus{State: "Abroad", Description: "In UK"}, LastAction: domain.UserAction{Relative: "1 hour ago"}},
		20: {ID: 20, Name: "Bob", Status: domain.UserStatus{State: "Okay"}, LastAction: domain.UserAction{Relative: "5 minutes ago"}},
	}}
	svc := newLateOCServiceWithClock(repo, client)

	late, err := svc.FindLateOCs(context.Background(), 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(late) != 1 {
		t.Fatalf("expected 1 late OC, got %d", len(late))
	}
	oc := late[0]
	if oc.ExecutedAt != nil {
		t.Error("expected still-waiting OC (ExecutedAt nil)")
	}
	if oc.DelaySec != 1800 {
		t.Errorf("expected 1800s delay, got %d", oc.DelaySec)
	}
	// Alice abroad → blocker; Bob okay → not
	var alice, bob domain.LateOCSlot
	for _, s := range oc.Slots {
		switch s.UserID {
		case 10:
			alice = s
		case 20:
			bob = s
		}
	}
	if !alice.IsBlocker {
		t.Error("expected Alice (Abroad) to be flagged as blocker")
	}
	if alice.UserName != "Alice" {
		t.Errorf("expected Alice name resolved, got %q", alice.UserName)
	}
	if alice.ItemAvailable != "✓" {
		t.Errorf("expected item available ✓, got %q", alice.ItemAvailable)
	}
	if bob.IsBlocker {
		t.Error("expected Bob (Okay) to NOT be a blocker")
	}
	if bob.ItemAvailable != "n/a" {
		t.Errorf("expected Bob item n/a, got %q", bob.ItemAvailable)
	}
}

func TestFindLateOCs_NotYetReadyIgnored(t *testing.T) {
	repo := &mockFactionRepo{
		planning: []domain.Crime{
			{ID: 1, Name: "Future OC", Status: "Planning", ReadyAt: fixedNow.Add(1 * time.Hour)},
		},
	}
	svc := newLateOCServiceWithClock(repo, &stubClient{})
	late, err := svc.FindLateOCs(context.Background(), 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(late) != 0 {
		t.Errorf("expected 0 late OCs for not-yet-ready crime, got %d", len(late))
	}
}

func TestFindLateOCs_RecruitingIgnored(t *testing.T) {
	repo := &mockFactionRepo{
		planning: []domain.Crime{
			{ID: 1, Name: "Recruiting OC", Status: "Recruiting", ReadyAt: fixedNow.Add(-1 * time.Hour)},
		},
	}
	svc := newLateOCServiceWithClock(repo, &stubClient{})
	late, _ := svc.FindLateOCs(context.Background(), 0)
	if len(late) != 0 {
		t.Errorf("expected 0 late OCs for recruiting crime, got %d", len(late))
	}
}

func TestFindLateOCs_HistoricalWithinWindow(t *testing.T) {
	readyAt := fixedNow.Add(-3 * time.Hour)
	executedAt := readyAt.Add(10 * time.Minute) // 10 min late
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			{
				ID: 5, Name: "Late Heist", Status: "Successful",
				ReadyAt: readyAt, ExecutedAt: &executedAt,
				Slots: []domain.CrimeSlot{{Label: "Robber", User: &domain.User{ID: 99}}},
			},
		},
	}
	client := &stubClient{users: map[int]*domain.User{
		99: {ID: 99, Name: "Carol"},
	}}
	svc := newLateOCServiceWithClock(repo, client)

	late, err := svc.FindLateOCs(context.Background(), 24)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(late) != 1 {
		t.Fatalf("expected 1 historical late OC, got %d", len(late))
	}
	if late[0].ExecutedAt == nil {
		t.Error("expected executed OC")
	}
	if late[0].DelaySec != 600 {
		t.Errorf("expected 600s delay, got %d", late[0].DelaySec)
	}
	if late[0].Slots[0].UserName != "Carol" {
		t.Errorf("expected name Carol resolved, got %q", late[0].Slots[0].UserName)
	}
}

func TestFindLateOCs_HistoricalOnTimeFiltered(t *testing.T) {
	readyAt := fixedNow.Add(-3 * time.Hour)
	executedAt := readyAt.Add(30 * time.Second) // under 5-min threshold
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			{ID: 5, Name: "On Time", Status: "Successful", ReadyAt: readyAt, ExecutedAt: &executedAt},
		},
	}
	svc := newLateOCServiceWithClock(repo, &stubClient{})
	late, _ := svc.FindLateOCs(context.Background(), 24)
	if len(late) != 0 {
		t.Errorf("expected on-time OC filtered out, got %d", len(late))
	}
}

func TestFindLateOCs_HistoricalIgnoredWhenNoLookback(t *testing.T) {
	readyAt := fixedNow.Add(-3 * time.Hour)
	executedAt := readyAt.Add(10 * time.Minute)
	repo := &mockFactionRepo{
		crimes: []domain.Crime{
			{ID: 5, Name: "Late Heist", Status: "Successful", ReadyAt: readyAt, ExecutedAt: &executedAt},
		},
	}
	svc := newLateOCServiceWithClock(repo, &stubClient{})
	// hours=0 → completed crimes not even fetched/considered
	late, _ := svc.FindLateOCs(context.Background(), 0)
	if len(late) != 0 {
		t.Errorf("expected historical OCs ignored with lookback=0, got %d", len(late))
	}
}

func TestFindLateOCs_SortedByDelayDesc(t *testing.T) {
	repo := &mockFactionRepo{
		planning: []domain.Crime{
			{ID: 1, Name: "Small Delay", Status: "Planning", ReadyAt: fixedNow.Add(-10 * time.Minute)},
			{ID: 2, Name: "Big Delay", Status: "Planning", ReadyAt: fixedNow.Add(-2 * time.Hour)},
		},
	}
	svc := newLateOCServiceWithClock(repo, &stubClient{})
	late, _ := svc.FindLateOCs(context.Background(), 0)
	if len(late) != 2 {
		t.Fatalf("expected 2 late OCs, got %d", len(late))
	}
	if late[0].ID != 2 {
		t.Errorf("expected biggest delay (id=2) first, got id=%d", late[0].ID)
	}
}
