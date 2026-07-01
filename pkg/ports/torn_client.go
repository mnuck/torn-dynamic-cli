package ports

import (
	"context"
	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// TornClient is a port for interacting with the Torn API.
type TornClient interface {
	GetCrime(ctx context.Context, id int) (*domain.Crime, error)
	GetUser(ctx context.Context, id int) (*domain.User, error)
	// Add more as needed
}
