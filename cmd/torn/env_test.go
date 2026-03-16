package main

import (
	"os"
	"testing"
)

func TestLoadEnvFile_MissingFileIssilent(t *testing.T) {
	// A missing .env file is not an error — it's optional
	err := LoadEnvFile("/tmp/nonexistent_torn_test.env")
	if err != nil {
		t.Errorf("expected nil error for missing file, got: %v", err)
	}
}

func TestLoadEnvFile_ParsesKeyValue(t *testing.T) {
	f, err := os.CreateTemp("", "torn_test_*.env")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(f.Name())

	f.WriteString("TORN_TEST_VAR=hello\n")
	f.Close()

	os.Unsetenv("TORN_TEST_VAR")
	defer os.Unsetenv("TORN_TEST_VAR")

	if err := LoadEnvFile(f.Name()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := os.Getenv("TORN_TEST_VAR"); got != "hello" {
		t.Errorf("expected 'hello', got '%s'", got)
	}
}

func TestLoadEnvFile_SkipsCommentsAndBlanks(t *testing.T) {
	f, err := os.CreateTemp("", "torn_test_*.env")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(f.Name())

	f.WriteString("# this is a comment\n\nTORN_TEST_VAR2=world\n")
	f.Close()

	os.Unsetenv("TORN_TEST_VAR2")
	defer os.Unsetenv("TORN_TEST_VAR2")

	if err := LoadEnvFile(f.Name()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := os.Getenv("TORN_TEST_VAR2"); got != "world" {
		t.Errorf("expected 'world', got '%s'", got)
	}
}

func TestLoadEnvFile_ValueCanContainEquals(t *testing.T) {
	// Values like BASE64==  should be preserved intact (SplitN with n=2)
	f, err := os.CreateTemp("", "torn_test_*.env")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(f.Name())

	f.WriteString("TORN_TEST_B64=abc=def==\n")
	f.Close()

	os.Unsetenv("TORN_TEST_B64")
	defer os.Unsetenv("TORN_TEST_B64")

	if err := LoadEnvFile(f.Name()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := os.Getenv("TORN_TEST_B64"); got != "abc=def==" {
		t.Errorf("expected 'abc=def==', got '%s'", got)
	}
}

func TestLoadEnvFile_DoesNotOverwriteExisting(t *testing.T) {
	f, err := os.CreateTemp("", "torn_test_*.env")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(f.Name())

	f.WriteString("TORN_TEST_EXISTING=fromfile\n")
	f.Close()

	os.Setenv("TORN_TEST_EXISTING", "fromenv")
	defer os.Unsetenv("TORN_TEST_EXISTING")

	if err := LoadEnvFile(f.Name()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := os.Getenv("TORN_TEST_EXISTING"); got != "fromenv" {
		t.Errorf("env var should not be overwritten: expected 'fromenv', got '%s'", got)
	}
}
