package services

import (
	"context"
	"sort"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

// GoodThugService identifies Thugs who have completed OCs and are ready for promotion.
type GoodThugService struct {
	repo ports.FactionRepository
}

func NewGoodThugService(repo ports.FactionRepository) *GoodThugService {
	return &GoodThugService{repo: repo}
}

// GoodThugReport holds the results of the analysis.
type GoodThugReport struct {
	Ready  []domain.GoodThug
	NotYet []domain.Member
}

// Analyze fetches members and completed crimes, then classifies Thugs.
func (s *GoodThugService) Analyze(ctx context.Context, days int) (GoodThugReport, error) {
	from := time.Now().AddDate(0, 0, -days)

	members, err := s.repo.GetMembers(ctx)
	if err != nil {
		return GoodThugReport{}, err
	}

	// Filter to Thugs only
	var thugs []domain.Member
	for _, m := range members {
		if m.Position == "Thug" {
			thugs = append(thugs, m)
		}
	}

	crimes, err := s.repo.GetCompletedCrimes(ctx, from)
	if err != nil {
		return GoodThugReport{}, err
	}

	// Count how many completed OCs each member participated in
	ocCount := make(map[int]int)
	for _, c := range crimes {
		for _, slot := range c.Slots {
			if slot.User != nil {
				ocCount[slot.User.ID]++
			}
		}
	}

	// Classify
	var ready []domain.GoodThug
	var notYet []domain.Member
	for _, t := range thugs {
		if count := ocCount[t.ID]; count > 0 {
			ready = append(ready, domain.GoodThug{Member: t, OCCount: count})
		} else {
			notYet = append(notYet, t)
		}
	}

	// Sort ready by OC count desc, then name
	sort.Slice(ready, func(i, j int) bool {
		if ready[i].OCCount != ready[j].OCCount {
			return ready[i].OCCount > ready[j].OCCount
		}
		return ready[i].Name < ready[j].Name
	})

	// Sort not-yet by days in faction desc
	sort.Slice(notYet, func(i, j int) bool {
		return notYet[i].DaysInFaction > notYet[j].DaysInFaction
	})

	return GoodThugReport{Ready: ready, NotYet: notYet}, nil
}
