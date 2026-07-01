package services

import (
	"context"
	"sort"
	"sync"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

// minMeaningfulDelay filters out normal execution jitter for historical OCs.
const minMeaningfulDelay = 5 * time.Minute

// LateOCService finds organized crimes delayed past their ready time.
type LateOCService struct {
	repo   ports.FactionRepository
	client ports.TornClient
	now    func() time.Time // injectable clock for testing
}

func NewLateOCService(repo ports.FactionRepository, client ports.TornClient) *LateOCService {
	return &LateOCService{repo: repo, client: client, now: time.Now}
}

// FindLateOCs returns currently-late OCs (planning) and, when lookbackHours > 0,
// historical OCs that executed late within the window. Currently-late OCs have
// their slots enriched with each member's live status to identify blockers.
func (s *LateOCService) FindLateOCs(ctx context.Context, lookbackHours int) ([]domain.LateOC, error) {
	now := s.now()

	planning, err := s.repo.GetPlanningCrimes(ctx)
	if err != nil {
		return nil, err
	}

	crimes := planning
	if lookbackHours > 0 {
		completed, err := s.repo.GetCompletedCrimes(ctx, time.Time{})
		if err != nil {
			return nil, err
		}
		crimes = append(crimes, completed...)
	}

	cutoff := now.Add(-time.Duration(lookbackHours) * time.Hour)

	var late []domain.LateOC
	for _, c := range crimes {
		if c.Status == "Recruiting" || c.ReadyAt.IsZero() {
			continue
		}

		if c.ExecutedAt != nil {
			// Historical: only meaningful, in-window delays.
			delay := c.ExecutedAt.Sub(c.ReadyAt)
			if lookbackHours == 0 || !c.ReadyAt.Before(now) || delay < minMeaningfulDelay || c.ReadyAt.Before(cutoff) {
				continue
			}
			late = append(late, buildLateOC(c, int64(delay.Seconds())))
		} else {
			// Currently late: ready_at in the past, not yet executed.
			if !c.ReadyAt.Before(now) {
				continue
			}
			late = append(late, buildLateOC(c, int64(now.Sub(c.ReadyAt).Seconds())))
		}
	}

	sort.Slice(late, func(i, j int) bool {
		return late[i].DelaySec > late[j].DelaySec
	})

	// Enrich still-waiting OCs with live member status to surface blockers.
	for i := range late {
		if late[i].ExecutedAt == nil {
			s.enrichStatuses(ctx, late[i].Slots)
		} else {
			s.enrichNames(ctx, late[i].Slots)
		}
	}

	return late, nil
}

func buildLateOC(c domain.Crime, delaySec int64) domain.LateOC {
	lo := domain.LateOC{
		ID:         c.ID,
		Name:       c.Name,
		ReadyAt:    c.ReadyAt,
		ExecutedAt: c.ExecutedAt,
		DelaySec:   delaySec,
	}
	for _, slot := range c.Slots {
		ls := domain.LateOCSlot{
			Position:      slot.Label,
			ItemAvailable: itemAvailStr(slot.ItemAvailable),
		}
		if slot.User != nil {
			ls.UserID = slot.User.ID
		}
		lo.Slots = append(lo.Slots, ls)
	}
	return lo
}

func itemAvailStr(avail *bool) string {
	if avail == nil {
		return "n/a"
	}
	if *avail {
		return "✓"
	}
	return "✗"
}

// enrichStatuses fetches live status for each slot concurrently and flags blockers.
func (s *LateOCService) enrichStatuses(ctx context.Context, slots []domain.LateOCSlot) {
	var wg sync.WaitGroup
	for i := range slots {
		if slots[i].UserID == 0 {
			continue
		}
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			u, err := s.client.GetUser(ctx, slots[idx].UserID)
			if err != nil || u == nil {
				return
			}
			slots[idx].UserName = u.Name
			slots[idx].StatusState = u.Status.State
			slots[idx].StatusDesc = u.Status.Description
			slots[idx].LastAction = u.LastAction.Relative
			slots[idx].IsBlocker = u.Status.State != "" && u.Status.State != "Okay"
		}(i)
	}
	wg.Wait()
}

// enrichNames fetches just the display name for each slot concurrently.
func (s *LateOCService) enrichNames(ctx context.Context, slots []domain.LateOCSlot) {
	var wg sync.WaitGroup
	for i := range slots {
		if slots[i].UserID == 0 {
			continue
		}
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			u, err := s.client.GetUser(ctx, slots[idx].UserID)
			if err != nil || u == nil {
				return
			}
			slots[idx].UserName = u.Name
		}(i)
	}
	wg.Wait()
}
