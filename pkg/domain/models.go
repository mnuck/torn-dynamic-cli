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

// Member represents a summary of a faction member for reporting.
type Member struct {
	ID            int
	Name          string
	Level         int
	Position      string
	DaysInFaction int
	IsInOC        bool
}

// GoodThug represents a Thug-position member who has completed at least one OC.
type GoodThug struct {
	Member
	OCCount int
}

// XanaxUsage represents a recorded instance of Xanax usage from the armory.
type XanaxUsage struct {
	Username string
	Count    int
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
	Relative  string
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
	Scope   int  // 0 means stepping-stone (spawns higher OC, no direct payout)
	Paid    bool // true if payout has already been made
	Items   []string
}

// CrimeSlot represents a slot in an organized crime.
type CrimeSlot struct {
	Position      string
	Label         string
	User          *User
	ItemAvailable *bool // nil = no item requirement
	IsSuccessful  bool
	Progress      int // Percentage 0-100
}

// LateOCSlot is a slot in a late OC, enriched with the member's current status.
type LateOCSlot struct {
	Position      string
	UserID        int
	UserName      string
	ItemAvailable string // "✓", "✗", or "n/a"
	StatusState   string
	StatusDesc    string
	LastAction    string
	IsBlocker     bool
}

// LateOC is an organized crime that became ready but was delayed.
type LateOC struct {
	ID         int
	Name       string
	ReadyAt    time.Time
	ExecutedAt *time.Time // nil = still waiting
	DelaySec   int64
	Slots      []LateOCSlot
}

// Hit represents a single outgoing attack in a history report.
type Hit struct {
	Timestamp   int64   // Unix timestamp of when the attack ended
	Attacker    string
	Defender    string
	Result      string
	RespectGain float64
	Link        string
}

// Freeloader represents a member who used faction Xanax but is not in any OC.
type Freeloader struct {
	Name          string
	XanaxCount    int
	Level         int
	Position      string
	DaysInFaction int
}
