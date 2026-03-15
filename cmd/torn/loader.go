package main

import (
	"encoding/json"
	"fmt"
)

// Simplified OpenAPI structs for what we actually need
type OpenAPISpec struct {
	Paths      map[string]PathItem `json:"paths"`
	Servers    []Server            `json:"servers"`
	Components Components          `json:"components"`
}

type Server struct {
	URL string `json:"url"`
}

type Components struct {
	Parameters map[string]Parameter `json:"parameters"`
}

// PathItem can have operations like GET, POST, but also common parameters
// We mostly care about GET for a CLI reader
type PathItem struct {
	Get *Operation `json:"get"`
	// Parameters common to all operations in this path
	Parameters []ParameterOrRef `json:"parameters"`
}

type Operation struct {
	Summary     string           `json:"summary"`
	Description string           `json:"description"`
	OperationID string           `json:"operationId"`
	Parameters  []ParameterOrRef `json:"parameters"`
}

// ParameterOrRef handles the fact that parameters can be inline or $ref
type ParameterOrRef struct {
	Parameter
	Ref string `json:"$ref"`
}

type Parameter struct {
	Name        string `json:"name"`
	In          string `json:"in"` // "query", "path"
	Description string `json:"description"`
	Required    bool   `json:"required"`
	// We might need schema to detect type, but for CLI strings often suffice
	// schema struct is complex, let's keep it simple for MVP or parse generic map
	Schema json.RawMessage `json:"schema"`
}

func LoadSpec(data []byte) (*OpenAPISpec, error) {
	var spec OpenAPISpec
	if err := json.Unmarshal(data, &spec); err != nil {
		return nil, fmt.Errorf("failed to parse openapi spec: %w", err)
	}

	return &spec, nil
}
