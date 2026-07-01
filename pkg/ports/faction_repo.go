package ports

import (
	"context"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// FactionRepository is a port for interacting with faction-related data.
type FactionRepository interface {
	GetMembers(ctx context.Context) ([]domain.Member, error)
	GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error)
	GetActiveCrimes(ctx context.Context) ([]domain.Crime, error)
	GetCompletedCrimes(ctx context.Context, from time.Time) ([]domain.Crime, error)
}
