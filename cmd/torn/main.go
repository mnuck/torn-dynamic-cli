package main

import (
	_ "embed"
	"fmt"
	"os"
)

//go:embed torn_openapi_v2.json
var specBytes []byte

func main() {
	// 0. Load .env file if it exists (optional)
	LoadEnvFile(".env")

	// 1. Load Spec from embedded bytes
	spec, err := LoadSpec(specBytes)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading spec: %v\n", err)
		os.Exit(1)
	}

	// 2. Build Commands
	rootCmd := BuildCommands(spec)

	// 3. Register hand-written report commands
	rootCmd.AddCommand(NewReportCmd())

	// 4. Execute
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}
