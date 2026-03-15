package main

import (
	"bufio"
	"os"
	"strings"
)

// LoadEnvFile reads a .env file and sets environment variables
// Lines starting with # are ignored, empty lines are skipped
// Format: KEY=VALUE (no quotes needed, but values can contain = signs)
func LoadEnvFile(filepath string) error {
	file, err := os.Open(filepath)
	if err != nil {
		// .env file is optional, so return silently if not found
		return nil
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		// Split on first = only
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}

		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])

		// Only set if not already set in environment
		if _, exists := os.LookupEnv(key); !exists {
			os.Setenv(key, value)
		}
	}

	return scanner.Err()
}
