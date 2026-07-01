package ports

import (
	"context"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

// DataRepository is a port for accessing historical status data (e.g. from BigQuery).
type DataRepository interface {
	GetMemberStatusAt(ctx context.Context, memberID int, timestamp time.Time) (*domain.UserStatus, error)
}
