package main

import (
	"testing"
)

func TestFormatDuration(t *testing.T) {
	tests := []struct {
		seconds int64
		want    string
	}{
		{30, "30s"},
		{60, "1m"},
		{90, "1m"},
		{300, "5m"},
		{3600, "1h"},
		{3660, "1h 1m"},
		{5400, "1h 30m"},
		{20940, "5h 49m"},
	}

	for _, tt := range tests {
		got := formatDuration(tt.seconds)
		if got != tt.want {
			t.Errorf("formatDuration(%d) = %q, want %q", tt.seconds, got, tt.want)
		}
	}
}

func TestFormatItemAvail(t *testing.T) {
	avail := &APIItemRequirement{IsAvailable: true}
	unavail := &APIItemRequirement{IsAvailable: false}

	if got := formatItemAvail(avail); got != "✓" {
		t.Errorf("formatItemAvail(true) = %q, want %q", got, "✓")
	}
	if got := formatItemAvail(unavail); got != "✗" {
		t.Errorf("formatItemAvail(false) = %q, want %q", got, "✗")
	}
	if got := formatItemAvail(nil); got != "n/a" {
		t.Errorf("formatItemAvail(nil) = %q, want %q", got, "n/a")
	}
}
