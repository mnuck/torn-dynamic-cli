package services

import (
	"context"
	"testing"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// MockTornClient is a mock implementation of ports.TornClient.
type MockTornClient struct{}

func (m *MockTornClient) GetCrime(ctx context.Context, id int) (*domain.Crime, error) {
	return nil, nil
}
func (m *MockTornClient) GetUser(ctx context.Context, id int) (*domain.User, error) {
	return nil, nil
}
func (m *MockTornClient) GetFactionMembers(ctx context.Context) ([]domain.Member, error) {
	return nil, nil
}
func (m *MockTornClient) GetMembers(ctx context.Context) ([]domain.Member, error) {
	return nil, nil
}
func (m *MockTornClient) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	return nil, nil
}
func (m *MockTornClient) GetCrimes(ctx context.Context, category string, from *time.Time) ([]domain.Crime, error) {
	return nil, nil
}
func (m *MockTornClient) GetAttacks(ctx context.Context, from time.Time) ([]domain.Hit, error) {
	return nil, nil
}

// MockDataRepo is a mock implementation of ports.DataRepository.
type MockDataRepo struct {
	MemberStatuses map[int]domain.UserStatus
}

func (m *MockDataRepo) GetMemberStatusAt(ctx context.Context, memberID int, timestamp time.Time) (*domain.UserStatus, error) {
	status, ok := m.MemberStatuses[memberID]
	if !ok {
		return nil, nil
	}
	return &status, nil
}

func TestIsCrimeLate(t *testing.T) {
	now := time.Now()
	readyAt := now.Add(-1 * time.Hour)
	executedAt := now

	crime := &domain.Crime{
		ID:        123,
		ReadyAt:   readyAt,
		ExecutedAt: &executedAt,
		Slots: []domain.CrimeSlot{
			{
				User: &domain.User{ID: 1, Name: "User 1"},
			},
			{
				User: &domain.User{ID: 2, Name: "User 2"},
			},
		},
	}

	repo := &MockDataRepo{
		MemberStatuses: map[int]domain.UserStatus{
			1: {State: "Okay", Description: "In Torn"},
			2: {State: "Abroad", Description: "In UK"},
		},
	}
	client := &MockTornClient{}
	service := NewCrimeService(client, repo)

	late, absent, err := service.IsCrimeLate(context.Background(), crime)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !late {
		t.Error("expected crime to be late")
	}

	if len(absent) != 1 {
		t.Errorf("expected 1 absent member, got %d", len(absent))
	}

	if absent[0].State != "Abroad" {
		t.Errorf("expected status Abroad, got %s", absent[0].State)
	}
}
