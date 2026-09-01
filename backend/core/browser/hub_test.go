package browser

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"
)

func TestPairingIsOneTimeAndDevicesAreUserScoped(t *testing.T) {
	hub, err := NewHub()
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 31, 10, 0, 0, 0, time.UTC)
	hub.now = func() time.Time { return now }

	pairing, err := hub.CreatePairing("user-1")
	if err != nil {
		t.Fatal(err)
	}
	paired, err := hub.PairExtension(PairExtensionInput{
		Code: pairing.Code, DeviceName: "Work Chrome", Browser: "Chrome", Version: "1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if paired.DeviceID == "" || paired.DeviceToken == "" {
		t.Fatalf("invalid pair result: %#v", paired)
	}
	if _, err := hub.PairExtension(PairExtensionInput{Code: pairing.Code}); !errors.Is(err, ErrPairingInvalid) {
		t.Fatalf("reused pairing error = %v, want ErrPairingInvalid", err)
	}
	if _, err := hub.AuthenticateDevice(paired.DeviceID, "wrong"); err == nil {
		t.Fatal("wrong device token authenticated")
	}
	if _, err := hub.AuthenticateDevice(paired.DeviceID, paired.DeviceToken); err != nil {
		t.Fatalf("valid device token rejected: %v", err)
	}
	if got := hub.ListDevices("user-1"); len(got) != 1 || got[0].Name != "Work Chrome" {
		t.Fatalf("user devices = %#v", got)
	}
	if got := hub.ListDevices("user-2"); len(got) != 0 {
		t.Fatalf("other user can see devices: %#v", got)
	}
	if err := hub.RevokeDevice("user-2", paired.DeviceID); !errors.Is(err, ErrDeviceNotFound) {
		t.Fatalf("cross-user revoke error = %v", err)
	}
}

func TestExpiredPairingIsRejected(t *testing.T) {
	hub, err := NewHub()
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 31, 10, 0, 0, 0, time.UTC)
	hub.now = func() time.Time { return now }
	pairing, err := hub.CreatePairing("user-1")
	if err != nil {
		t.Fatal(err)
	}
	now = now.Add(defaultPairingTTL + time.Second)
	if _, err := hub.PairExtension(PairExtensionInput{Code: pairing.Code}); !errors.Is(err, ErrPairingInvalid) {
		t.Fatalf("expired pairing error = %v", err)
	}
}

func TestCallRoutesCommandAndResultToOwnedOnlineDevice(t *testing.T) {
	hub, err := NewHub()
	if err != nil {
		t.Fatal(err)
	}
	pairing, _ := hub.CreatePairing("user-1")
	paired, _ := hub.PairExtension(PairExtensionInput{Code: pairing.Code})
	connection := &deviceConnection{
		send: make(chan commandEnvelope, 1), done: make(chan struct{}),
		pending: make(map[string]chan commandResponse),
	}
	if err := hub.Attach(paired.DeviceID, connection); err != nil {
		t.Fatal(err)
	}
	go func() {
		command := <-connection.send
		if command.Action != "snapshot" {
			connection.resolve(resultEnvelope{Type: "result", ID: command.ID, OK: false, Error: &protocolError{Code: "BAD_ACTION"}})
			return
		}
		connection.resolve(resultEnvelope{Type: "result", ID: command.ID, OK: true, Result: json.RawMessage(`{"revision":2}`)})
	}()

	raw, err := hub.Call(context.Background(), "user-1", paired.DeviceID, "snapshot", SessionInput{SessionID: "bs_1"})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"revision":2}` {
		t.Fatalf("result = %s", raw)
	}
	if _, err := hub.Call(context.Background(), "user-2", paired.DeviceID, "snapshot", SessionInput{}); !errors.Is(err, ErrDeviceNotFound) {
		t.Fatalf("cross-user call error = %v", err)
	}
	if _, err := hub.Call(context.Background(), "user-1", paired.DeviceID, "raw_cdp", map[string]any{}); err == nil {
		t.Fatal("unsupported action was accepted")
	}
}

func TestOnlineDevicePrefersConfiguredDesktopBrowser(t *testing.T) {
	t.Setenv("LAZYMIND_BROWSER_PREFERRED_DEVICE_BROWSER", "Electron WebContentsView")
	hub, err := NewHub()
	if err != nil {
		t.Fatal(err)
	}
	chromeConnection := &deviceConnection{done: make(chan struct{})}
	desktopConnection := &deviceConnection{done: make(chan struct{})}
	now := time.Now().UTC()
	hub.devices["chrome"] = &deviceRecord{
		ID: "chrome", UserID: "user-1", Browser: "Chrome",
		LastSeenAt: now, Connection: chromeConnection,
	}
	hub.devices["desktop"] = &deviceRecord{
		ID: "desktop", UserID: "user-1", Browser: "Electron WebContentsView",
		LastSeenAt: now.Add(-time.Hour), Connection: desktopConnection,
	}

	selected, err := hub.onlineDevice("user-1", "")
	if err != nil {
		t.Fatal(err)
	}
	if selected != desktopConnection {
		t.Fatalf("selected %#v, want Desktop embedded browser", selected)
	}
}

func TestToolTokenRoundTripAndExpiry(t *testing.T) {
	hub, err := NewHub()
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 31, 10, 15, 0, 0, time.UTC)
	hub.signer.now = func() time.Time { return now }
	token, err := hub.ToolToken("user-1")
	if err != nil {
		t.Fatal(err)
	}
	claims, err := hub.VerifyToolToken(token)
	if err != nil || claims.Subject != "user-1" {
		t.Fatalf("claims=%#v err=%v", claims, err)
	}
	now = time.Unix(claims.Expires, 0).Add(time.Second)
	if _, err := hub.VerifyToolToken(token); err == nil {
		t.Fatal("expired token verified")
	}
}
