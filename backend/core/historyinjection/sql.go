package historyinjection

import (
	"fmt"
	"strings"
)

const (
	ownerIDToken          = "{{OWNER_USER_ID}}"
	ownerNameToken        = "{{OWNER_USER_NAME}}"
	workflowResourceToken = "{{WORKFLOW_RESOURCE_ID}}"
	workflowRevisionToken = "{{WORKFLOW_REVISION_NO}}"
)

func renderSQL(source string, values map[string]string) string {
	for token, value := range values {
		source = strings.ReplaceAll(source, token, strings.ReplaceAll(value, "'", "''"))
	}
	return source
}

// splitSQLStatements is deliberately small but quote-aware. Exported SQL uses
// ordinary single-quoted SQL literals, including multiline JSON/text values.
// Semicolons inside those literals must never terminate a statement.
func splitSQLStatements(source string) ([]string, error) {
	var statements []string
	var current strings.Builder
	inQuote := false
	lineComment := false
	for i := 0; i < len(source); i++ {
		char := source[i]
		if lineComment {
			if char == '\n' {
				lineComment = false
				current.WriteByte(char)
			}
			continue
		}
		if !inQuote && char == '-' && i+1 < len(source) && source[i+1] == '-' {
			lineComment = true
			i++
			continue
		}
		if char == '\'' {
			current.WriteByte(char)
			if inQuote && i+1 < len(source) && source[i+1] == '\'' {
				current.WriteByte(source[i+1])
				i++
				continue
			}
			inQuote = !inQuote
			continue
		}
		if char == ';' && !inQuote {
			if statement := strings.TrimSpace(current.String()); statement != "" {
				statements = append(statements, statement)
			}
			current.Reset()
			continue
		}
		current.WriteByte(char)
	}
	if inQuote {
		return nil, fmt.Errorf("history injection SQL contains an unterminated string literal")
	}
	if statement := strings.TrimSpace(current.String()); statement != "" {
		statements = append(statements, statement)
	}
	return statements, nil
}
