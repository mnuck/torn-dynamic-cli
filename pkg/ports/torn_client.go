package ports

import (
	"context"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// TornClient is a port for interacting with the Torn API.
type TornClient interface {
	GetCrime(ctx context.Context, id int) (*domain.Crime, error)
	GetUser(ctx context.Context, id int) (*domain.User, error)
	GetMembers(ctx context.Context) ([]domain.Member, error)
	GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error)
	GetCrimes(ctx context.Context, category string, from *time.Time) ([]domain.Crime, error)
	GetAttacks(ctx context.Context, from time.Time) ([]domain.Hit, error)
}
