package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

// pathVariant holds one spec path that maps to a single CLI command.
// Multiple variants can collide (e.g. /user/profile and /user/{id}/profile).
type pathVariant struct {
	path       string
	pathParams []string
}

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

	// Collect all path variants per leaf command so colliding spec paths
	// (e.g. /faction/members and /faction/{id}/members) are merged.
	// Map from leaf command pointer to its accumulated variants.
	type leafEntry struct {
		cmd     *cobra.Command
		variants []pathVariant
	}
	var leaves []leafEntry

	for path, item := range spec.Paths {
		// Only handle GET for now
		if item.Get == nil {
			continue
		}

		// Split path into segments using "/"
		// e.g. "/user/{id}/profile" -> ["user", "{id}", "profile"]
		// Path-param segments ({…}) are collapsed; they become flags instead.
		// So /user/{id}/profile -> `torn user profile --id ...`
		// /user/profile -> `torn user profile` (implicitly current user)

		parts := strings.Split(strings.Trim(path, "/"), "/")
		var commandParts []string
		pathParams := []string{}

		for _, p := range parts {
			if strings.HasPrefix(p, "{") && strings.HasSuffix(p, "}") {
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

			// If this is the leaf (last part), collect the variant and register flags
			if i == len(commandParts)-1 {
				leafCmd := parent
				op := item.Get

				// Register Flags (idempotent via nil-check)
				// 1. Path Params (e.g. --id)
				for _, pp := range pathParams {
					if leafCmd.Flags().Lookup(pp) == nil {
						leafCmd.Flags().String(pp, "", fmt.Sprintf("Path parameter: %s", pp))
					}
				}

				// 2. Query Params from Operation
				for _, paramOrRef := range op.Parameters {
					p := ResolveParameter(spec, paramOrRef)
					if p.Name != "" && p.In == "query" {
						if leafCmd.Flags().Lookup(p.Name) == nil {
							leafCmd.Flags().String(p.Name, "", p.Description)
						}
					}
				}

				// 3. Query Params from PathItem (common parameters)
				for _, paramOrRef := range item.Parameters {
					p := ResolveParameter(spec, paramOrRef)
					if p.Name != "" && p.In == "query" {
						if leafCmd.Flags().Lookup(p.Name) == nil {
							leafCmd.Flags().String(p.Name, "", p.Description)
						}
					}
				}

				// 4. Auto-Paging flag
				if leafCmd.Flags().Lookup("all") == nil {
					leafCmd.Flags().Bool("all", false, "Automatically fetch all pages by following _metadata.next")
				}

				leaves = append(leaves, leafEntry{
					cmd: leafCmd,
					variants: []pathVariant{{
						path:       path,
						pathParams: pathParams,
					}},
				})
			}
		}
	}

	// Merge variants for colliding commands (same leaf command pointer).
	// Then set RunE once per leaf, selecting the correct variant at runtime.
	variantMap := make(map[*cobra.Command][]pathVariant)
	for _, le := range leaves {
		variantMap[le.cmd] = append(variantMap[le.cmd], le.variants...)
	}
	for cmd, variants := range variantMap {
		cmd.RunE = func(c *cobra.Command, args []string) error {
			return ExecuteRequest(c, spec, variants)
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
