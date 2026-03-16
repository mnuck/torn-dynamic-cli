package main

import (
	"testing"
)

func TestClassifyThugs_ReadyWhenOCCount(t *testing.T) {
	thugs := []memberInfo{
		{ID: 1, Name: "Alice"},
		{ID: 2, Name: "Bob"},
	}
	ocCount := map[int]int{1: 3} // Alice has 3 OCs; Bob has 0

	ready, notYet := classifyThugs(thugs, ocCount)

	if len(ready) != 1 {
		t.Fatalf("expected 1 ready thug, got %d", len(ready))
	}
	if ready[0].Name != "Alice" {
		t.Errorf("expected Alice in ready, got %s", ready[0].Name)
	}
	if ready[0].OCCount != 3 {
		t.Errorf("expected OCCount=3, got %d", ready[0].OCCount)
	}
	if len(notYet) != 1 {
		t.Fatalf("expected 1 not-yet thug, got %d", len(notYet))
	}
	if notYet[0].Name != "Bob" {
		t.Errorf("expected Bob in notYet, got %s", notYet[0].Name)
	}
}

func TestClassifyThugs_AllReady(t *testing.T) {
	thugs := []memberInfo{
		{ID: 1, Name: "Alice"},
		{ID: 2, Name: "Bob"},
	}
	ocCount := map[int]int{1: 2, 2: 1}

	ready, notYet := classifyThugs(thugs, ocCount)

	if len(ready) != 2 {
		t.Errorf("expected 2 ready, got %d", len(ready))
	}
	if len(notYet) != 0 {
		t.Errorf("expected 0 not-yet, got %d", len(notYet))
	}
}

func TestClassifyThugs_NoneReady(t *testing.T) {
	thugs := []memberInfo{
		{ID: 1, Name: "Alice"},
		{ID: 2, Name: "Bob"},
	}
	ocCount := map[int]int{} // nobody has OCs

	ready, notYet := classifyThugs(thugs, ocCount)

	if len(ready) != 0 {
		t.Errorf("expected 0 ready, got %d", len(ready))
	}
	if len(notYet) != 2 {
		t.Errorf("expected 2 not-yet, got %d", len(notYet))
	}
}

func TestClassifyThugs_Empty(t *testing.T) {
	ready, notYet := classifyThugs(nil, map[int]int{})
	if len(ready) != 0 || len(notYet) != 0 {
		t.Errorf("expected empty results for empty input, got ready=%d notYet=%d", len(ready), len(notYet))
	}
}
