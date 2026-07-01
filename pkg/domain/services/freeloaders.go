package services

import (
	"context"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

// FreeloaderService contains business logic for identifying members who use faction Xanax but aren't in OCs.
type FreeloaderService struct {
	repo ports.FactionRepository
}

// NewFreeloaderService creates a new instance of FreeloaderService.
func NewFreeloaderService(repo ports.FactionRepository) *FreeloaderService {
	return &FreeloaderService{
		repo: repo,
	}
}

// IdentifyFreeloaders finds members who used Xanax but are not in any OC within the specified lookback window.
func (s *FreeloaderService) IdentifyFreeloaders(ctx context.Context, lookbackHours int) ([]domain.Freeloader, int, error) {
	// 1. Fetch members
	members, err := s.repo.GetMembers(ctx)
	if err != nil {
		return nil, 0, err
	}
	memberMap := make(map[string]domain.Member) // name -> member
	idToMember := make(map[int]domain.Member)    // id -> member
	for _, m := range members {
		memberMap[m.Name] = m
		idToMember[m.ID] = m
	}

	// 2. Fetch Xanax usage from news
	xanaxUsages, err := s.repo.GetArmoryNews(ctx, time.Now().Add(-time.Duration(lookbackHours)*time.Hour))
	if err != nil {
		return nil, 0, err
	}

	xanaxCounts := make(map[string]int)
	for _, u := range xanaxUsages {
		xanaxCounts[u.Username]++
	}

	// 3. Fetch OC participants
	ocParticipants := make(map[int]bool)

	// Active crimes
	activeCrimes, err := s.repo.GetActiveCrimes(ctx)
	if err != nil {
		return nil, 0, err
	}
	for _, c := range activeCrimes {
		for _, slot := range c.Slots {
			if slot.User != nil {
				ocParticipants[slot.User.ID] = true
			}
		}
	}

	// Completed crimes
	completedCrimes, err := s.repo.GetCompletedCrimes(ctx, time.Now().Add(-time.Duration(lookbackHours)*time.Hour))
	if err != nil {
		return nil, 0, err
	}
	for _, c := range completedCrimes {
		for _, slot := range c.Slots {
			if slot.User != nil {
				ocParticipants[slot.User.ID] = true
			}
		}
	}

	// 4. Classify
	var freeloaders []domain.Freeloader
	compliantCount := 0

	for username, count := range xanaxCounts {
		member, exists := memberMap[username]
		if !exists {
			continue
		}
		if ocParticipants[member.ID] {
			compliantCount++
		} else {
			freeloaders = append(freeloaders, domain.Freeloader{
				Name:          username,
				XanaxCount:    count,
				Level:         member.Level,
				Position:      member.Position,
				DaysInFaction: member.DaysInFaction,
			})
		}
	}

	return freeloaders, compliantCount, nil
}
