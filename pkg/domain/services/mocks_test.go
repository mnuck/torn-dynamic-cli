package services

import (
	"context"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// mockFactionRepo is a shared in-memory FactionRepository for service-level tests.
type mockFactionRepo struct {
	members  []domain.Member
	crimes   []domain.Crime
	planning []domain.Crime
	active   []domain.Crime
	news     []domain.XanaxUsage
}

func (m *mockFactionRepo) GetMembers(ctx context.Context) ([]domain.Member, error) {
	return m.members, nil
}

func (m *mockFactionRepo) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	return m.news, nil
}

func (m *mockFactionRepo) GetActiveCrimes(ctx context.Context) ([]domain.Crime, error) {
	return m.active, nil
}

func (m *mockFactionRepo) GetPlanningCrimes(ctx context.Context) ([]domain.Crime, error) {
	return m.planning, nil
}

func (m *mockFactionRepo) GetCompletedCrimes(ctx context.Context, from time.Time) ([]domain.Crime, error) {
	return m.crimes, nil
}
