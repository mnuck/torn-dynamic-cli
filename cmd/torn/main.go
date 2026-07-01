package main

import (
	_ "embed"
	"fmt"
	"os"

	"github.com/mnuck/torn-dynamic-cli/pkg/adapters/faction"
	"github.com/mnuck/torn-dynamic-cli/pkg/adapters/tornapi"
	"github.com/mnuck/torn-dynamic-cli/pkg/domain/services"
)

//go:embed torn_openapi_v2.json
var specBytes []byte

func main() {
	LoadEnvFile(".env")

	spec, err := LoadSpec(specBytes)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading spec: %v\n", err)
		os.Exit(1)
	}

	// Composition root: wire adapters and services
	apiKey := os.Getenv("TORN_API_KEY")
	httpClient := tornapi.NewHTTPClient("https://api.torn.com/v2", apiKey)
	factionRepo := faction.NewTornFactionRepo(httpClient)
	freeloaderService := services.NewFreeloaderService(factionRepo)
	hitService := services.NewHitService(httpClient)

	rootCmd := BuildCommands(spec)
	rootCmd.AddCommand(NewReportCmd(freeloaderService, hitService))

	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}
