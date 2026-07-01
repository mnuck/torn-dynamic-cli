package faction

import (
	"context"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

// TornFactionRepo is an adapter that implements ports.FactionRepository.
type TornFactionRepo struct {
	client ports.TornClient
}

func NewTornFactionRepo(client ports.TornClient) *TornFactionRepo {
	return &TornFactionRepo{
		client: client,
	}
}

func (r *TornFactionRepo) GetMembers(ctx context.Context) ([]domain.Member, error) {
	return r.client.GetMembers(ctx)
}

func (r *TornFactionRepo) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	return r.client.GetArmoryNews(ctx, from)
}

func (r *TornFactionRepo) GetActiveCrimes(ctx context.Context) ([]domain.Crime, error) {
	return r.client.GetCrimes(ctx, "available", nil)
}

func (r *TornFactionRepo) GetCompletedCrimes(ctx context.Context, from time.Time) ([]domain.Crime, error) {
	if from.IsZero() {
		return r.client.GetCrimes(ctx, "completed", nil)
	}
	return r.client.GetCrimes(ctx, "completed", &from)
}
