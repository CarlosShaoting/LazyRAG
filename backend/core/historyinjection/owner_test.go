package historyinjection

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestResolveOwnerSupportsAuthServiceEnvelope(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/auth/login":
			_ = json.NewEncoder(response).Encode(map[string]any{
				"code": 200, "message": "success", "data": map[string]string{"access_token": "test-token"},
			})
		case "/auth/me":
			if request.Header.Get("Authorization") != "Bearer test-token" {
				response.WriteHeader(http.StatusUnauthorized)
				return
			}
			_ = json.NewEncoder(response).Encode(map[string]any{
				"code": 200, "message": "success", "data": map[string]string{"user_id": "target-user", "username": "admin"},
			})
		default:
			response.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	owner, err := resolveOwnerOnce(t.Context(), server.Client(), server.URL, "admin", "admin")
	if err != nil {
		t.Fatal(err)
	}
	if owner.ID != "target-user" || owner.Username != "admin" {
		t.Fatalf("unexpected owner: %#v", owner)
	}
}
