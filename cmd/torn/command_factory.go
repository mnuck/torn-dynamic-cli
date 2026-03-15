package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

func BuildCommands(spec *OpenAPISpec) *cobra.Command {
	rootCmd := &cobra.Command{
		Use:   "torn",
		Short: "Dynamic CLI for Torn API",
	}

	// Add global flag for API Key
	rootCmd.PersistentFlags().String("key", "", "Torn API Key")

	// Helper to track created commands to avoid duplicates
	// key: "user", value: cmd
	// key: "user/profile", value: cmd
	cmdCache := make(map[string]*cobra.Command)
	cmdCache[""] = rootCmd

	for path, item := range spec.Paths {
		// Only handle GET for now
		if item.Get == nil {
			continue
		}

		// Split path into segments using "/"
		// e.g. "/user/{id}/profile" -> ["user", "{id}", "profile"]
		// We will ignore {id} segments for command structure, and treat them as required flags or arguments later.
		// Actually, for Torn API v2:
		// /user/profile
		// /user/{id}/profile
		// These might conflict if we map both to `torn user profile`.

		// Strategy:
		// Use the literal segments as command names.
		// If a segment is {id}, we treat it as a parameter, NOT a command node, effectively collapsing it.
		// So /user/{id}/profile -> `torn user profile --id ...`
		// /user/profile -> `torn user profile` (implicitly current user)

		parts := strings.Split(strings.Trim(path, "/"), "/")
		var commandParts []string
		pathParams := []string{}

		for _, p := range parts {
			if strings.HasPrefix(p, "{") && strings.HasSuffix(p, "}") {
				// It's a path param
				paramName := strings.Trim(p, "{}")
				pathParams = append(pathParams, paramName)
			} else {
				commandParts = append(commandParts, p)
			}
		}

		// Build the command hierarchy
		// e.g. ["user", "profile"]
		parent := rootCmd
		currentPath := ""

		for i, part := range commandParts {
			if currentPath == "" {
				currentPath = part
			} else {
				currentPath = currentPath + "/" + part
			}

			if existing, ok := cmdCache[currentPath]; ok {
				parent = existing
			} else {
				newCmd := &cobra.Command{
					Use:   part,
					Short: fmt.Sprintf("Command for %s", part),
				}
				parent.AddCommand(newCmd)
				cmdCache[currentPath] = newCmd
				parent = newCmd
			}

			// If this is the leaf (last part), attach the operation
			if i == len(commandParts)-1 {
				// This is the command that executes request
				// We need to capture the operation and path params in the closure or struct
				op := item.Get
				fullPath := path
				pParams := pathParams

				parent.RunE = func(cmd *cobra.Command, args []string) error {
					// Logic to execute request
					return ExecuteRequest(cmd, spec, fullPath, op, pParams)
				}

				// Register Flags
				// 1. Path Params (e.g. --id)
				for _, pp := range pParams {
					if parent.Flags().Lookup(pp) == nil {
						parent.Flags().String(pp, "", fmt.Sprintf("Path parameter: %s", pp))
					}
				}

				// 2. Query Params from Operation
				for _, paramOrRef := range op.Parameters {
					// Start simplistic: we assume inline parameters or we need a resolver.
					// For now, let's assume if it has a Name, use it.
					// If it's a ref, we skip (MVP limitation - we need to resolve refs for full support)
					// The loader Struct has a Ref field.
					// Resolving standard refs is complex.
					// HOWEVER, `go-swagger` failed because of this. Python solution worked because we ignored implementation details.

					// Let's rely on just Name if present. If Ref, we need to lookup in Components.
					p := ResolveParameter(spec, paramOrRef)
					if p.Name != "" && p.In == "query" {
						if parent.Flags().Lookup(p.Name) == nil {
							parent.Flags().String(p.Name, "", p.Description)
						}
					}
				}

				// 3. Query Params from PathItem (common parameters)
				for _, paramOrRef := range item.Parameters {
					p := ResolveParameter(spec, paramOrRef)
					if p.Name != "" && p.In == "query" {
						if parent.Flags().Lookup(p.Name) == nil {
							parent.Flags().String(p.Name, "", p.Description)
						}
					}
				}

				// 4. Auto-Paging flag
				if parent.Flags().Lookup("all") == nil {
					parent.Flags().Bool("all", false, "Automatically fetch all pages by following _metadata.next")
				}
			}
		}
	}

	return rootCmd
}

func ResolveParameter(spec *OpenAPISpec, p ParameterOrRef) Parameter {
	if p.Ref != "" {
		// Simple Ref resolver: "#/components/parameters/Name"
		parts := strings.Split(p.Ref, "/")
		if len(parts) > 0 {
			name := parts[len(parts)-1]
			if resolved, ok := spec.Components.Parameters[name]; ok {
				return resolved
			}
		}
	}
	return p.Parameter
}
