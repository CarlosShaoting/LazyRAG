package common

import (
	"encoding/hex"
	"os"
	"strings"

	"github.com/google/uuid"
)

// GenerateID returns a random 32-char hex id (UUID v4, no dashes). Each call is independent.
func GenerateID() string {
	u := uuid.New()
	return hex.EncodeToString(u[:])
}

// ReaderUseCacheEnabled reads LAZYMIND_READER_CACHE (default true).
func ReaderUseCacheEnabled() bool {
	v := strings.TrimSpace(os.Getenv("LAZYMIND_READER_CACHE"))
	if v == "" {
		return true
	}
	switch strings.ToLower(v) {
	case "false", "0", "no", "off":
		return false
	default:
		return true
	}
}
