package services

import (
	"context"
	"sort"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

// HitService contains business logic for filtering and processing attack history.
type HitService struct {
	client ports.TornClient
}

// NewHitService creates a new instance of HitService.
func NewHitService(client ports.TornClient) *HitService {
	return &HitService{client: client}
}

// GetAttackHistory fetches and filters outgoing attacks for a specific member by name.
func (s *HitService) GetAttackHistory(ctx context.Context, userName string, days int) ([]domain.Hit, error) {
	from := time.Now().AddDate(0, 0, -days)
	attacks, err := s.client.GetAttacks(ctx, from)
	if err != nil {
		return nil, err
	}

	var userAttacks []domain.Hit
	for _, a := range attacks {
		if a.Attacker == userName {
			userAttacks = append(userAttacks, a)
		}
	}

	sort.Slice(userAttacks, func(i, j int) bool {
		return userAttacks[i].Timestamp < userAttacks[j].Timestamp
	})

	return userAttacks, nil
}
