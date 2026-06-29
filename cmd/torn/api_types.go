package main

import "encoding/json"

// apiErrorEnvelope detects the Torn API error envelope:
// {"error": {"code": N, "error": "message"}}
type apiErrorEnvelope struct {
	Error *struct {
		Code  int    `json:"code"`
		Error string `json:"error"`
	} `json:"error"`
}

// apiPageMeta extracts pagination links. Two shapes exist in the wild:
//
//	{"_metadata": {"links": {"next": "...", "prev": "..."}}}
//	{"_metadata": {"next": "..."}}   (flat form, some endpoints)
type apiPageMeta struct {
	Metadata *struct {
		Links *struct {
			Next string `json:"next"`
			Prev string `json:"prev"`
		} `json:"links"`
		Next string `json:"next"` // flat fallback
	} `json:"_metadata"`
}

// APIMember is one entry from /v2/faction/members → "members" array.
type APIMember struct {
	ID            int    `json:"id"`
	Name          string `json:"name"`
	Level         int    `json:"level"`
	Position      string `json:"position"`
	DaysInFaction int    `json:"days_in_faction"`
	IsInOC        bool   `json:"is_in_oc"`
}

// MembersPage is one page from /v2/faction/members.
type MembersPage struct {
	Members []APIMember `json:"members"`
}

// APINewsItem is one entry from /v2/faction/news → "news" array.
type APINewsItem struct {
	Text string `json:"text"`
}

// NewsPage is one page from /v2/faction/news.
type NewsPage struct {
	News []APINewsItem `json:"news"`
}

// APIRewards holds the reward details for a crime.
// Payout is json.RawMessage so we can distinguish null (not yet paid) from absent.
type APIRewards struct {
	Scope   int64           `json:"scope"`
	Money   int64           `json:"money"`
	Respect int64           `json:"respect"`
	Payout  json.RawMessage `json:"payout"`
}

// APIPositionInfo is the position label within a crime slot.
type APIPositionInfo struct {
	Label string `json:"label"`
}

// APISlotUser is the user assigned to a crime slot.
type APISlotUser struct {
	ID int64 `json:"id"`
}

// APIItemRequirement is the item requirement for a crime slot.
type APIItemRequirement struct {
	IsAvailable bool `json:"is_available"`
}

// APICSlot is one slot within a crime.
type APICSlot struct {
	PositionInfo    *APIPositionInfo    `json:"position_info"`
	User            *APISlotUser        `json:"user"`
	ItemRequirement *APIItemRequirement `json:"item_requirement"`
}

// APICrime is one entry from /v2/faction/crimes → "crimes" array.
type APICrime struct {
	ID         int64       `json:"id"`
	Name       string      `json:"name"`
	Status     string      `json:"status"`
	ReadyAt    int64       `json:"ready_at"`
	ExecutedAt int64       `json:"executed_at"`
	Slots      []APICSlot  `json:"slots"`
	Rewards    *APIRewards `json:"rewards"`
}

// CrimesPage is one page from /v2/faction/crimes.
type CrimesPage struct {
	Crimes []APICrime `json:"crimes"`
}

// APIAttackPerson is an attacker or defender in an attack record.
type APIAttackPerson struct {
	Name string `json:"name"`
}

// APIAttack is one entry from /v2/faction/attacks → "attacks" array.
type APIAttack struct {
	Attacker    *APIAttackPerson `json:"attacker"`
	Defender    *APIAttackPerson `json:"defender"`
	Ended       int64            `json:"ended"`
	Code        string           `json:"code"`
	Result      string           `json:"result"`
	RespectGain float64          `json:"respect_gain"`
}

// AttacksPage is one page from /v2/faction/attacks.
type AttacksPage struct {
	Attacks []APIAttack `json:"attacks"`
}

// APIStatus is the status block within a user profile.
type APIStatus struct {
	State       string `json:"state"`
	Description string `json:"description"`
}

// APILastAction is the last_action block within a user profile.
type APILastAction struct {
	Relative string `json:"relative"`
}

// APIProfile is the "profile" object from /v2/user/{id}/profile.
type APIProfile struct {
	Name       string         `json:"name"`
	Status     *APIStatus     `json:"status"`
	LastAction *APILastAction `json:"last_action"`
}

// ProfilePage is the response from /v2/user/{id}/profile.
type ProfilePage struct {
	Profile *APIProfile `json:"profile"`
}

// formatItemAvail replaces the old gjson-based formatBool.
// Returns "✓", "✗", or "n/a" depending on whether the item is available.
func formatItemAvail(req *APIItemRequirement) string {
	if req == nil {
		return "n/a"
	}
	if req.IsAvailable {
		return "✓"
	}
	return "✗"
}
