package services

import (
	"context"
	"sort"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

const lateThresholdSec = 30 * 60 // 30 minutes

// UnpaidOC is a completed crime that has not yet been paid out.
type UnpaidOC struct {
	Crime    domain.Crime
	DelaySec int64
	IsLate   bool
}

// OCPayoutService identifies completed OCs that still need to be paid out.
type OCPayoutService struct {
	repo ports.FactionRepository
}

func NewOCPayoutService(repo ports.FactionRepository) *OCPayoutService {
	return &OCPayoutService{repo: repo}
}

// GetUnpaidOCs returns completed crimes that have not yet been paid, oldest first.
func (s *OCPayoutService) GetUnpaidOCs(ctx context.Context) ([]UnpaidOC, error) {
	crimes, err := s.repo.GetCompletedCrimes(ctx, time.Time{}) // zero = no from filter
	if err != nil {
		return nil, err
	}

	var unpaid []UnpaidOC
	for _, c := range crimes {
		// scope=0 means stepping-stone crime — no direct payout
		if c.Rewards.Scope == 0 {
			continue
		}
		// already paid
		if c.Rewards.Paid {
			continue
		}
		// not yet executed
		if c.ExecutedAt == nil {
			continue
		}

		delaySec := int64(c.ExecutedAt.Sub(c.ReadyAt).Seconds())
		unpaid = append(unpaid, UnpaidOC{
			Crime:    c,
			DelaySec: delaySec,
			IsLate:   delaySec > lateThresholdSec,
		})
	}

	// Oldest executed first — pay those first
	sort.Slice(unpaid, func(i, j int) bool {
		return unpaid[i].Crime.ExecutedAt.Before(*unpaid[j].Crime.ExecutedAt)
	})

	return unpaid, nil
}
