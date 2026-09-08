package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"
)

const sqliteTestToken = "test-token"

func TestSQLiteServerSerializesSameDatabaseAndParallelizesDifferentDatabases(t *testing.T) {
	tempDir := t.TempDir()
	server, err := newSQLiteHTTPServer(sqliteTestToken, map[string]string{
		"core":    filepath.Join(tempDir, "core.db"),
		"lazyllm": filepath.Join(tempDir, "lazyllm.db"),
	}, time.Minute)
	if err != nil {
		t.Fatalf("create sqlite server: %v", err)
	}
	defer server.Close()
	httpServer := httptest.NewServer(server.Handler())
	defer httpServer.Close()

	transaction := postSQLiteTestRequest(t, httpServer.URL, "/v1/begin", sqliteRequest{DB: "core"})
	postSQLiteTestRequest(t, httpServer.URL, "/v1/execute", sqliteRequest{
		DB:   "core",
		TxID: transaction.TxID,
		SQL:  "CREATE TABLE held (id INTEGER PRIMARY KEY)",
	})

	sameDatabaseDone := make(chan error, 1)
	go func() {
		_, err := doSQLiteTestRequest(httpServer.URL, "/v1/query", sqliteRequest{DB: "core", SQL: "SELECT 1"})
		sameDatabaseDone <- err
	}()
	select {
	case err := <-sameDatabaseDone:
		t.Fatalf("same-database request completed before transaction release: %v", err)
	case <-time.After(100 * time.Millisecond):
	}

	differentDatabaseDone := make(chan error, 1)
	go func() {
		_, err := doSQLiteTestRequest(
			httpServer.URL,
			"/v1/query",
			sqliteRequest{DB: "lazyllm", SQL: "SELECT 1"},
		)
		differentDatabaseDone <- err
	}()
	select {
	case err := <-differentDatabaseDone:
		if err != nil {
			t.Fatalf("different-database request failed: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("different-database request was blocked by core transaction")
	}

	postSQLiteTestRequest(t, httpServer.URL, "/v1/commit", sqliteRequest{DB: "core", TxID: transaction.TxID})
	select {
	case err := <-sameDatabaseDone:
		if err != nil {
			t.Fatalf("same-database request failed after release: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("same-database request did not resume after commit")
	}
}

func TestSQLiteServerExpiresAbandonedTransaction(t *testing.T) {
	server, err := newSQLiteHTTPServer("test-token", map[string]string{
		"core": filepath.Join(t.TempDir(), "core.db"),
	}, 50*time.Millisecond)
	if err != nil {
		t.Fatalf("create sqlite server: %v", err)
	}
	defer server.Close()
	httpServer := httptest.NewServer(server.Handler())
	defer httpServer.Close()

	postSQLiteTestRequest(t, httpServer.URL, "/v1/begin", sqliteRequest{DB: "core"})
	requestDone := make(chan error, 1)
	go func() {
		_, err := doSQLiteTestRequest(httpServer.URL, "/v1/query", sqliteRequest{DB: "core", SQL: "SELECT 1"})
		requestDone <- err
	}()
	select {
	case err := <-requestDone:
		if err != nil {
			t.Fatalf("request after transaction expiry failed: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("abandoned transaction did not release database queue")
	}
}

func postSQLiteTestRequest(t *testing.T, baseURL, path string, request sqliteRequest) sqliteResponse {
	t.Helper()
	response, err := doSQLiteTestRequest(baseURL, path, request)
	if err != nil {
		t.Fatalf("POST %s: %v", path, err)
	}
	return response
}

func doSQLiteTestRequest(baseURL, path string, request sqliteRequest) (sqliteResponse, error) {
	body, err := json.Marshal(request)
	if err != nil {
		return sqliteResponse{}, err
	}
	httpRequest, err := http.NewRequest(http.MethodPost, baseURL+path, bytes.NewReader(body))
	if err != nil {
		return sqliteResponse{}, err
	}
	httpRequest.Header.Set("Authorization", "Bearer "+sqliteTestToken)
	httpRequest.Header.Set("Content-Type", "application/json")
	httpResponse, err := http.DefaultClient.Do(httpRequest)
	if err != nil {
		return sqliteResponse{}, err
	}
	defer httpResponse.Body.Close()
	var response sqliteResponse
	if err := json.NewDecoder(httpResponse.Body).Decode(&response); err != nil {
		return sqliteResponse{}, err
	}
	if response.Error != "" {
		return sqliteResponse{}, &sqliteTestError{message: response.Error}
	}
	return response, nil
}

type sqliteTestError struct {
	message string
}

func (err *sqliteTestError) Error() string {
	return err.message
}
