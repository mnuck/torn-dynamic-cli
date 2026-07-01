package main

import (
	"context"
	"testing"
	"time"

	"github.com/mnuck/torn-dynamic-cli/pkg/domain"
	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
)

// mockHitClient is a mock TornClient that returns a fixed list of hits.
type mockHitClient struct {
	hits []domain.Hit
}

func (m *mockHitClient) GetAttacks(ctx context.Context, from time.Time) ([]domain.Hit, error) {
	return m.hits, nil
}
func (m *mockHitClient) GetCrime(ctx context.Context, id int) (*domain.Crime, error)          { return nil, nil }
func (m *mockHitClient) GetUser(ctx context.Context, id int) (*domain.User, error)            { return nil, nil }
func (m *mockHitClient) GetMembers(ctx context.Context) ([]domain.Member, error)              { return nil, nil }
func (m *mockHitClient) GetArmoryNews(ctx context.Context, from time.Time) ([]domain.XanaxUsage, error) {
	return nil, nil
}
func (m *mockHitClient) GetCrimes(ctx context.Context, category string, from *time.Time) ([]domain.Crime, error) {
	return nil, nil
}

func makeHit(attacker, defender, result, code string, ts int64, respect float64) domain.Hit {
	link := ""
	if code != "" {
		link = "https://www.torn.com/loader.php?sid=attackLog&ID=" + code
	}
	return domain.Hit{
		Attacker:    attacker,
		Defender:    defender,
		Timestamp:   ts,
		Result:      result,
		RespectGain: respect,
		Link:        link,
	}
}

func TestFilterHits_MatchesByName(t *testing.T) {
	client := &mockHitClient{hits: []domain.Hit{
		makeHit("Alice", "Enemy1", "Attacked", "abc123", 1700000000, 1.5),
		makeHit("Bob", "Enemy2", "Attacked", "def456", 1700000001, 2.0),
	}}
	svc := services.NewHitService(client)
	hits, err := svc.GetAttackHistory(context.Background(), "Alice", 7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(hits) != 1 {
		t.Fatalf("expected 1 hit for Alice, got %d", len(hits))
	}
	if hits[0].Defender != "Enemy1" {
		t.Errorf("expected defender Enemy1, got %s", hits[0].Defender)
	}
	if hits[0].RespectGain != 1.5 {
		t.Errorf("expected respect 1.5, got %f", hits[0].RespectGain)
	}
}

func TestFilterHits_BuildsLinkFromCode(t *testing.T) {
	client := &mockHitClient{hits: []domain.Hit{
		makeHit("Alice", "Enemy", "Attacked", "abc123", 1700000000, 1.0),
	}}
	svc := services.NewHitService(client)
	hits, _ := svc.GetAttackHistory(context.Background(), "Alice", 7)

	expected := "https://www.torn.com/loader.php?sid=attackLog&ID=abc123"
	if hits[0].Link != expected {
		t.Errorf("expected link %s, got %s", expected, hits[0].Link)
	}
}

func TestFilterHits_EmptyLinkWhenNoCode(t *testing.T) {
	client := &mockHitClient{hits: []domain.Hit{
		makeHit("Alice", "Enemy", "Attacked", "", 1700000000, 0.0),
	}}
	svc := services.NewHitService(client)
	hits, _ := svc.GetAttackHistory(context.Background(), "Alice", 7)

	if hits[0].Link != "" {
		t.Errorf("expected empty link when code is missing, got %s", hits[0].Link)
	}
}

func TestFilterHits_MultipleHits(t *testing.T) {
	client := &mockHitClient{hits: []domain.Hit{
		makeHit("Alice", "E1", "Attacked", "c1", 1700000001, 1.0),
		makeHit("Alice", "E2", "Mugged", "c2", 1700000002, 2.0),
	}}
	svc := services.NewHitService(client)
	hits, _ := svc.GetAttackHistory(context.Background(), "Alice", 7)

	if len(hits) != 2 {
		t.Errorf("expected 2 hits, got %d", len(hits))
	}
}

func TestFilterHits_NoMatches(t *testing.T) {
	client := &mockHitClient{hits: []domain.Hit{
		makeHit("Bob", "Enemy", "Attacked", "abc", 1700000000, 1.0),
	}}
	svc := services.NewHitService(client)
	hits, _ := svc.GetAttackHistory(context.Background(), "Alice", 7)

	if len(hits) != 0 {
		t.Errorf("expected 0 hits when name doesn't match, got %d", len(hits))
	}
}

func TestFilterHits_EmptyPages(t *testing.T) {
	client := &mockHitClient{hits: nil}
	svc := services.NewHitService(client)
	hits, _ := svc.GetAttackHistory(context.Background(), "Alice", 7)

	if len(hits) != 0 {
		t.Errorf("expected 0 hits for empty input, got %d", len(hits))
	}
}
