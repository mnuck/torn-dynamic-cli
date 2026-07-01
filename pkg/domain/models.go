package domain

import (
	"time"
)

// User represents a Torn user.
type User struct {
	ID            int
	Name          string
	Level         int
	Rank          string
	Role          string
	Status        UserStatus
	LastAction    UserAction
	DonatorStatus  string
	SignedUp      time.Time
	Revivable     bool
}

// UserStatus represents the current status of a user (e.g. Okay, Abroad, Traveling).
type UserStatus struct {
	State       string
	Description string
	Details     string
	Until       *time.Time
}

// UserAction represents the last action taken by a user.
type UserAction struct {
	Status    string
	Timestamp time.Time
}

// Crime represents an organized crime.
type Crime struct {
	ID              int
	Name            string
	Difficulty      int
	Status          string
	CreatedAt       time.Time
	PlanningAt      time.Time
	ReadyAt         time.Time
	ExecutedAt      *time.Time
	ExpiredAt       *time.Time
	PreviousCrimeID *int
	Rewards         CrimeRewards
	Slots           []CrimeSlot
}

// CrimeRewards contains the results of a crime.
type CrimeRewards struct {
	Money   int
	Respect int
	Items   []string
}

// CrimeSlot represents a slot in an organized crime.
type CrimeSlot struct {
	Position     string
	Label        string
	User         *User
	IsSuccessful  bool
	Progress    int // Percentage 0-100
}
