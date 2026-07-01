package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestGenerateCompanyReport_Basic(t *testing.T) {
	profileJSON := `{"company": {"name":"TestCo","rating":5,"company_type":8}}`
	detailsJSON := `{"company": {"weekly_income":1200,"daily_income":200,"daily_customers":5,"weekly_customers":30}}`
	listJSON := `{"company": {"companies": [
        {"rating":5,"weekly_income":1500},
        {"rating":5,"weekly_income":1200},
        {"rating":5,"weekly_income":800},
        {"rating":4,"weekly_income":1100}
    ]}}`

	var profile map[string]interface{}
	var details map[string]interface{}
	var list map[string]interface{}

	if err := json.Unmarshal([]byte(profileJSON), &profile); err != nil {
		t.Fatalf("failed to unmarshal profile: %v", err)
	}
	if err := json.Unmarshal([]byte(detailsJSON), &details); err != nil {
		t.Fatalf("failed to unmarshal details: %v", err)
	}
	if err := json.Unmarshal([]byte(listJSON), &list); err != nil {
		t.Fatalf("failed to unmarshal list: %v", err)
	}

	report, err := generateCompanyReport(profile, details, list)
	if err != nil {
		t.Fatalf("generateCompanyReport returned error: %v", err)
	}

	// Basic sanity checks
	if !strings.Contains(report, "Company: TestCo (5★)") {
		t.Errorf("report missing company header: %s", report)
	}
	if !strings.Contains(report, "Rank: #2 / 3") {
		t.Errorf("expected rank #2 out of 3, got: %s", report)
	}
	if !strings.Contains(report, "Shops below you: 1") {
		t.Errorf("expected shops below you = 1, got: %s", report)
	}
	if !strings.Contains(report, "LOW risk of starring down") {
		t.Errorf("expected LOW risk, got: %s", report)
	}
}
