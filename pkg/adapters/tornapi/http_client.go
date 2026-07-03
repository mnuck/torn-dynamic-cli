package tornapi

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
)

type apiMetadata struct {
	Links struct {
		Next string `json:"next"`
		Prev string `json:"prev"`
	} `json:"links"`
}

type apiError struct {
	Code  int    `json:"code"`
	Error string `json:"error"`
}

type baseResponse struct {
	Metadata *apiMetadata `json:"_metadata,omitempty"`
	Error    *apiError    `json:"error,omitempty"`
}

// HTTPClient is an adapter that implements ports.TornClient and handles pagination.
type HTTPClient struct {
	baseURL string
	apiKey  string
	client  *http.Client
}

func NewHTTPClient(baseURL, apiKey string) *HTTPClient {
	return &HTTPClient{
		baseURL: baseURL,
		apiKey:  apiKey,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (c *HTTPClient) do(ctx context.Context, urlStr string, target interface{}) (string, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "ApiKey "+c.apiKey)

	resp, err := c.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var apiErr apiError
		if err := json.NewDecoder(resp.Body).Decode(&apiErr); err == nil {
			return "", fmt.Errorf("API error %d: %s", apiErr.Code, apiErr.Error)
		}
		return "", fmt.Errorf("HTTP error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	// Check for error in 200 OK response
	var errCheck baseResponse
	if err := json.Unmarshal(body, &errCheck); err == nil && errCheck.Error != nil {
		return "", fmt.Errorf("API error: %s", errCheck.Error.Error)
	}

	if err := json.Unmarshal(body, target); err != nil {
		return "", err
	}

	return string(body), nil
}

func (c *HTTPClient) GetMembers(ctx context.Context) ([]domain.Member, error) {
	var allMembers []domain.Member
	nextURL := fmt.Sprintf("%s/faction/members", c.baseURL)

	for nextURL != "" {
		var resp struct {
			Members []struct {
				ID            int    `json:"id"`
				Name          string `json:"name"`
				Level         int    `json:"level"`
				Position      string `json:"position"`
				DaysInFaction int    `json:"days_in_faction"`
				IsInOC        bool   `json:"is_in_oc"`
				Status        struct {
					State       string `json:"state"`
					Description string `json:"description"`
					Details     string `json:"details"`
				} `json:"status"`
				LastAction struct {
					Status   string `json:"status"`
					Relative string `json:"relative"`
				} `json:"last_action"`
			} `json:"members"`
			Metadata *apiMetadata `json:"_metadata"`
		}

		_, err := c.do(ctx, nextURL, &resp)
		if err != nil {
			return nil, err
		}

		for _, m := range resp.Members {
			allMembers = append(allMembers, domain.Member{
				ID:            m.ID,
				Name:          m.Name,
				Level:         m.Level,
				Position:      m.Position,
				DaysInFaction: m.DaysInFaction,
				IsInOC:        m.IsInOC,
				Status: domain.UserStatus{
					State:       m.Status.State,
					Description: m.Status.Description,
					Details:     m.Status.Details,
				},
				LastAction: domain.UserAction{
					Status:   m.LastAction.Status,
					Relative: m.LastAction.Relative,
				},
			})
		}

		if resp.Metadata != nil && resp.Metadata.Links.Next != "" {
			nextURL = resp.Metadata.Links.Next
		} else {
			nextURL = ""
		}
	}
	return allMembers, nil
}

func (c *HTTPClient) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	var allUsages []domain.XanaxUsage
	nextURL := fmt.Sprintf("%s/faction/news?cat=armoryAction&striptags=true&from=%d", c.baseURL, from.Unix())

	for nextURL != "" {
		var resp struct {
			News []struct {
				Text string `json:"text"`
			} `json:"news"`
			Metadata *apiMetadata `json:"_metadata"`
		}

		_, err := c.do(ctx, nextURL, &resp)
		if err != nil {
			return nil, err
		}

		for _, n := range resp.News {
			// Simple check: "Username used one of the faction's Xanax items"
			if strings.HasPrefix(n.Text, " used one of the faction's Xanax items") {
				parts := strings.Split(n.Text, " ")
				if len(parts) > 0 {
					allUsages = append(allUsages, domain.XanaxUsage{
						Username: parts[0],
						Count:    1,
					})
				}
			}
		}

		if resp.Metadata != nil && resp.Metadata.Links.Next != "" {
			nextURL = resp.Metadata.Links.Next
		} else {
			nextURL = ""
		}
	}
	return allUsages, nil
}

func (c *HTTPClient) GetCrimes(ctx context.Context, category string, from *time.Time) ([]domain.Crime, error) {
	var allCrimes []domain.Crime
	nextURL := fmt.Sprintf("%s/faction/crimes?cat=%s", c.baseURL, category)
	if from != nil {
		nextURL += fmt.Sprintf("&from=%d", from.Unix())
	}

	for nextURL != "" {
		var resp struct {
			Crimes []struct {
				ID         int    `json:"id"`
				Name       string `json:"name"`
				Difficulty int    `json:"difficulty"`
				Status     string `json:"status"`
				ReadyAt    int64  `json:"ready_at"`
				ExecutedAt int64  `json:"executed_at"`
				ExpiredAt  int64  `json:"expired_at"`
				Rewards    *struct {
					Money   int64           `json:"money"`
					Respect int64           `json:"respect"`
					Scope   int             `json:"scope"`
					Payout  json.RawMessage `json:"payout"`
				} `json:"rewards"`
				Slots []struct {
					PositionInfo *struct {
						Label string `json:"label"`
					} `json:"position_info"`
					User *struct {
						ID int `json:"id"`
					} `json:"user"`
					ItemRequirement *struct {
						IsAvailable bool `json:"is_available"`
					} `json:"item_requirement"`
				} `json:"slots"`
			} `json:"crimes"`
			Metadata *apiMetadata `json:"_metadata"`
		}

		_, err := c.do(ctx, nextURL, &resp)
		if err != nil {
			return nil, err
		}

		for _, cr := range resp.Crimes {
			crime := domain.Crime{
				ID:         cr.ID,
				Name:       cr.Name,
				Difficulty: cr.Difficulty,
				Status:     cr.Status,
			}
			if cr.ReadyAt > 0 {
				crime.ReadyAt = time.Unix(cr.ReadyAt, 0)
			}
			if cr.ExecutedAt > 0 {
				t := time.Unix(cr.ExecutedAt, 0)
				crime.ExecutedAt = &t
			}
			if cr.ExpiredAt > 0 {
				t := time.Unix(cr.ExpiredAt, 0)
				crime.ExpiredAt = &t
			}
			if cr.Rewards != nil {
				paid := len(cr.Rewards.Payout) > 0 && string(cr.Rewards.Payout) != "null"
				crime.Rewards = domain.CrimeRewards{
					Money:   int(cr.Rewards.Money),
					Respect: int(cr.Rewards.Respect),
					Scope:   cr.Rewards.Scope,
					Paid:    paid,
				}
			}
			for _, s := range cr.Slots {
				slot := domain.CrimeSlot{}
				if s.PositionInfo != nil {
					slot.Label = s.PositionInfo.Label
				}
				if s.User != nil && s.User.ID > 0 {
					slot.User = &domain.User{ID: s.User.ID}
				}
				if s.ItemRequirement != nil {
					avail := s.ItemRequirement.IsAvailable
					slot.ItemAvailable = &avail
				}
				crime.Slots = append(crime.Slots, slot)
			}
			allCrimes = append(allCrimes, crime)
		}

		if resp.Metadata != nil && resp.Metadata.Links.Next != "" {
			nextURL = resp.Metadata.Links.Next
		} else {
			nextURL = ""
		}
	}
	return allCrimes, nil
}

func (c *HTTPClient) GetUser(ctx context.Context, id int) (*domain.User, error) {
	url := fmt.Sprintf("%s/user/%d/profile", c.baseURL, id)
	var resp struct {
		Profile struct {
			ID     int    `json:"id"`
			Name   string `json:"name"`
			Level  int    `json:"level"`
			Rank   string `json:"rank"`
			Role   string `json:"role"`
			Status *struct {
				State       string `json:"state"`
				Description string `json:"description"`
			} `json:"status"`
			LastAction *struct {
				Relative string `json:"relative"`
			} `json:"last_action"`
		} `json:"profile"`
	}

	_, err := c.do(ctx, url, &resp)
	if err != nil {
		return nil, err
	}

	u := &domain.User{
		ID:    resp.Profile.ID,
		Name:  resp.Profile.Name,
		Level: resp.Profile.Level,
		Rank:  resp.Profile.Rank,
		Role:  resp.Profile.Role,
	}
	if resp.Profile.Status != nil {
		u.Status = domain.UserStatus{
			State:       resp.Profile.Status.State,
			Description: resp.Profile.Status.Description,
		}
	}
	if resp.Profile.LastAction != nil {
		u.LastAction = domain.UserAction{Relative: resp.Profile.LastAction.Relative}
	}
	return u, nil
}

func (c *HTTPClient) GetCrime(ctx context.Context, id int) (*domain.Crime, error) {
	url := fmt.Sprintf("%s/crime/%d", c.baseURL, id)
	var resp struct {
		Crime domain.Crime `json:"crime"`
	}
	_, err := c.do(ctx, url, &resp)
	if err != nil {
		return nil, err
	}
	return &resp.Crime, nil
}

var xanaxPattern = regexp.MustCompile(`^(\S+) used one of the faction's Xanax items$`)

func (c *HTTPClient) GetAttacks(ctx context.Context, from time.Time) ([]domain.Hit, error) {
	var allHits []domain.Hit
	nextURL := fmt.Sprintf("%s/faction/attacks?filters=out&from=%d", c.baseURL, from.Unix())

	for nextURL != "" {
		var resp struct {
			Attacks []struct {
				Attacker *struct {
					Name string `json:"name"`
				} `json:"attacker"`
				Defender *struct {
					Name string `json:"name"`
				} `json:"defender"`
				Ended       int64   `json:"ended"`
				Code        string  `json:"code"`
				Result      string  `json:"result"`
				RespectGain float64 `json:"respect_gain"`
			} `json:"attacks"`
			Metadata *apiMetadata `json:"_metadata"`
		}

		_, err := c.do(ctx, nextURL, &resp)
		if err != nil {
			return nil, err
		}

		for _, a := range resp.Attacks {
			attackerName := ""
			if a.Attacker != nil {
				attackerName = a.Attacker.Name
			}
			defenderName := ""
			if a.Defender != nil {
				defenderName = a.Defender.Name
			}
			link := ""
			if a.Code != "" {
				link = fmt.Sprintf("https://www.torn.com/loader.php?sid=attackLog&ID=%s", a.Code)
			}
			allHits = append(allHits, domain.Hit{
				Timestamp:   a.Ended,
				Attacker:    attackerName,
				Defender:    defenderName,
				Result:      a.Result,
				RespectGain: a.RespectGain,
				Link:        link,
			})
		}

		if resp.Metadata != nil && resp.Metadata.Links.Next != "" {
			nextURL = resp.Metadata.Links.Next
		} else {
			nextURL = ""
		}
	}
	return allHits, nil
}
