package main

import (
	"context"
	"testing"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
)

// mockFactionRepo is a simple in-memory FactionRepository for testing.
type mockFactionRepo struct {
	members []domain.Member
	crimes  []domain.Crime
}

func (m *mockFactionRepo) GetMembers(ctx context.Context) ([]domain.Member, error) {
	return m.members, nil
}
func (m *mockFactionRepo) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	return nil, nil
}
func (m *mockFactionRepo) GetActiveCrimes(ctx context.Context) ([]domain.Crime, error) {
	return nil, nil
}
func (m *mockFactionRepo) GetCompletedCrimes(ctx context.Context, from time.Time) ([]domain.Crime, error) {
	return m.crimes, nil
}

func thugsWithOCs(members []domain.Member, ocParticipants map[int]int) ([]domain.Member, []domain.Crime) {
	var crimes []domain.Crime
	for memberID, count := range ocParticipants {
		for i := 0; i < count; i++ {
			crimes = append(crimes, domain.Crime{
				ID:     i + 1,
				Status: "Successful",
				Slots:  []domain.CrimeSlot{{User: &domain.User{ID: memberID}}},
			})
		}
	}
	return members, crimes
}

func TestClassifyThugs_ReadyWhenOCCount(t *testing.T) {
	members := []domain.Member{
		{ID: 1, Name: "Alice", Position: "Thug"},
		{ID: 2, Name: "Bob", Position: "Thug"},
	}
	members, crimes := thugsWithOCs(members, map[int]int{1: 3})

	repo := &mockFactionRepo{members: members, crimes: crimes}
	svc := services.NewGoodThugService(repo)
	report, err := svc.Analyze(context.Background(), 14)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(report.Ready) != 1 {
		t.Fatalf("expected 1 ready thug, got %d", len(report.Ready))
	}
	if report.Ready[0].Name != "Alice" {
		t.Errorf("expected Alice in ready, got %s", report.Ready[0].Name)
	}
	if report.Ready[0].OCCount != 3 {
		t.Errorf("expected OCCount=3, got %d", report.Ready[0].OCCount)
	}
	if len(report.NotYet) != 1 {
		t.Fatalf("expected 1 not-yet thug, got %d", len(report.NotYet))
	}
	if report.NotYet[0].Name != "Bob" {
		t.Errorf("expected Bob in notYet, got %s", report.NotYet[0].Name)
	}
}

func TestClassifyThugs_AllReady(t *testing.T) {
	members := []domain.Member{
		{ID: 1, Name: "Alice", Position: "Thug"},
		{ID: 2, Name: "Bob", Position: "Thug"},
	}
	members, crimes := thugsWithOCs(members, map[int]int{1: 2, 2: 1})

	repo := &mockFactionRepo{members: members, crimes: crimes}
	svc := services.NewGoodThugService(repo)
	report, err := svc.Analyze(context.Background(), 14)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(report.Ready) != 2 {
		t.Errorf("expected 2 ready, got %d", len(report.Ready))
	}
	if len(report.NotYet) != 0 {
		t.Errorf("expected 0 not-yet, got %d", len(report.NotYet))
	}
}

func TestClassifyThugs_NoneReady(t *testing.T) {
	members := []domain.Member{
		{ID: 1, Name: "Alice", Position: "Thug"},
		{ID: 2, Name: "Bob", Position: "Thug"},
	}
	repo := &mockFactionRepo{members: members, crimes: nil}
	svc := services.NewGoodThugService(repo)
	report, err := svc.Analyze(context.Background(), 14)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(report.Ready) != 0 {
		t.Errorf("expected 0 ready, got %d", len(report.Ready))
	}
	if len(report.NotYet) != 2 {
		t.Errorf("expected 2 not-yet, got %d", len(report.NotYet))
	}
}

func TestClassifyThugs_Empty(t *testing.T) {
	repo := &mockFactionRepo{}
	svc := services.NewGoodThugService(repo)
	report, err := svc.Analyze(context.Background(), 14)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(report.Ready) != 0 || len(report.NotYet) != 0 {
		t.Errorf("expected empty results for empty input, got ready=%d notYet=%d", len(report.Ready), len(report.NotYet))
	}
}

func TestClassifyThugs_NonThugsExcluded(t *testing.T) {
	members := []domain.Member{
		{ID: 1, Name: "Alice", Position: "Thug"},
		{ID: 2, Name: "Bob", Position: "Henchman"}, // not a Thug
	}
	members, crimes := thugsWithOCs(members, map[int]int{1: 1, 2: 5})

	repo := &mockFactionRepo{members: members, crimes: crimes}
	svc := services.NewGoodThugService(repo)
	report, err := svc.Analyze(context.Background(), 14)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Bob is Henchman — should not appear in either list
	if len(report.Ready)+len(report.NotYet) != 1 {
		t.Errorf("expected only 1 thug total, got %d", len(report.Ready)+len(report.NotYet))
	}
}
