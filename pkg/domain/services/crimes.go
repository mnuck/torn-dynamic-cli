package services

import (
	"context"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/ports"
)

// CrimeService contains business logic related to organized crimes.
type CrimeService struct {
	client ports.TornClient
	repo   ports.DataRepository
}

// NewCrimeService creates a new instance of CrimeService.
func NewCrimeService(client ports.TornClient, repo ports.DataRepository) *CrimeService {
	return &CrimeService{
		client: client,
		repo:   repo,
	}
}

// IsCrimeLate checks if a crime was delayed due to member absence at the moment it was ready.
func (s *CrimeService) IsCrimeLate(ctx context.Context, crime *domain.Crime) (bool, []domain.UserStatus, error) {
	if crime.ExecutedAt == nil {
		return false, nil, nil // Not executed yet
	}

	readyAt := crime.ReadyAt
	if crime.ReadyAt.IsZero() {
		// If ReadyAt is not set, maybe it's based on something else? 
		// For now, let's assume ReadyAt is the key.
		return false, nil, nil
	}

	var absentMembers []domain.UserStatus

	for _, slot := range crime.Slots {
		if slot.User == nil {
			continue
		}

		// Check if member was in a status other than "Okay" at ready time.
		// In a real app, we'd want to check if they were "Away" OR "Traveling" OR "Hospital" etc.
		// Here we just check their status at the moment it was ready.
		status, err := s.repo.GetMemberStatusAt(ctx, slot.User.ID, readyAt)
		if err != nil {
			// If we can't get status, we can't be sure they were present.
			// In a real app, we might want to return an error or a warning.
			continue
		}

		if status != nil && status.State != "Okay" {
			absentMembers = append(absentMembers, *status)
		}
	}

	isLate := len(absentMembers) > 0
	return isLate, absentMembers, nil
}
