import {
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";

import { axiosInstance } from "@/components/request";
import {
  embeddedBrowserCommand,
  embeddedBrowserState,
  hasDesktopEmbeddedBrowser,
  onEmbeddedBrowserState,
  setEmbeddedBrowserBounds,
  type DesktopEmbeddedBrowserAction,
  type DesktopEmbeddedBrowserState,
} from "@/runtime/desktopBridge";
import { apiUrl, coreApiUrl } from "@/runtime/apiBase";
import { isDesktopRuntime } from "@/runtime/mode";
import { unwrapApiData } from "@/modules/dataSource/api/unwrap";

import "./index.scss";

const PROTOCOL_VERSION = "1";
const PANEL_WIDTH_STORAGE_KEY = "lazymind.desktopEmbeddedBrowser.width";
const DEFAULT_PANEL_WIDTH = 620;
const MIN_PANEL_WIDTH = 380;
const CHAT_MIN_WIDTH = 360;

const EMPTY_STATE: DesktopEmbeddedBrowserState = {
  open: false,
  visible: false,
  loading: false,
  session_id: "",
  url: "",
  title: "",
  can_go_back: false,
  can_go_forward: false,
};

interface PairingResult {
  code: string;
}

interface DeviceCredentials {
  device_id: string;
  device_token: string;
}

interface BrowserCommandMessage {
  type: "command";
  id: string;
  action: DesktopEmbeddedBrowserAction;
  deadline_ms?: number;
  payload?: Record<string, unknown>;
}

interface DesktopEmbeddedBrowserProps {
  onVisibilityChange?: (visible: boolean) => void;
}

function initialPanelWidth(): number {
  try {
    const stored = Number(localStorage.getItem(PANEL_WIDTH_STORAGE_KEY));
    if (Number.isFinite(stored) && stored >= MIN_PANEL_WIDTH) {
      return Math.min(stored, maximumPanelWidth());
    }
  } catch {
    // Use the default width when storage is unavailable.
  }
  return DEFAULT_PANEL_WIDTH;
}

function maximumPanelWidth(): number {
  return Math.max(MIN_PANEL_WIDTH, Math.min(1200, window.innerWidth - CHAT_MIN_WIDTH));
}

function browserSocketURL(): string {
  const url = new URL(apiUrl("/api/browser/v1/connect"), window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

async function pairDesktopBrowser(): Promise<DeviceCredentials> {
  const pairingResponse = await axiosInstance.post(
    coreApiUrl("browser/manage/pairings"),
    {},
    { silentError: true } as never,
  );
  const pairing = unwrapApiData<PairingResult>(pairingResponse.data);
  if (!pairing?.code) throw new Error("Browser Gateway did not return a pairing code");

  const response = await fetch(apiUrl("/api/browser/v1/pair"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: pairing.code,
      device_name: "LazyMind Desktop Embedded Browser",
      browser: "Electron WebContentsView",
      version: "1",
    }),
  });
  const body = (await response.json().catch(() => ({}))) as Partial<DeviceCredentials> & {
    error?: { message?: string };
  };
  if (!response.ok || !body.device_id || !body.device_token) {
    throw new Error(body.error?.message || `Desktop browser pairing failed (HTTP ${response.status})`);
  }
  return { device_id: body.device_id, device_token: body.device_token };
}

function useDesktopBrowserGateway(enabled: boolean) {
  const [connectionState, setConnectionState] = useState<
    "disabled" | "connecting" | "connected" | "error"
  >(enabled ? "connecting" : "disabled");

  useEffect(() => {
    if (!enabled) return undefined;
    let stopped = false;
    let socket: WebSocket | null = null;
    let credentials: DeviceCredentials | null = null;
    let reconnectTimer: number | undefined;
    let reconnectAttempt = 0;
    let commandChain = Promise.resolve();

    const scheduleReconnect = () => {
      if (stopped) return;
      window.clearTimeout(reconnectTimer);
      const delay = Math.min(1000 * 2 ** reconnectAttempt, 30000);
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => void connect(), delay);
    };

    const sendCommandResult = async (currentSocket: WebSocket, message: BrowserCommandMessage) => {
      if (Number(message.deadline_ms) > 0 && Date.now() > Number(message.deadline_ms)) {
        if (currentSocket.readyState === WebSocket.OPEN) {
          currentSocket.send(JSON.stringify({
            type: "result",
            id: message.id,
            ok: false,
            error: { code: "ACTION_TIMEOUT", message: "命令到达 Desktop 时已经过期" },
          }));
        }
        return;
      }
      let result;
      try {
        result = await embeddedBrowserCommand(message.action, message.payload || {});
      } catch (error) {
        result = {
          ok: false as const,
          error: { code: "ACTION_FAILED", message: String((error as Error)?.message || error) },
        };
      }
      if (currentSocket.readyState !== WebSocket.OPEN) return;
      currentSocket.send(JSON.stringify(result.ok
        ? { type: "result", id: message.id, ok: true, result: result.result || {} }
        : { type: "result", id: message.id, ok: false, error: result.error }));
    };

    const handleMessage = (currentSocket: WebSocket, rawMessage: string) => {
      let message: Record<string, unknown>;
      try {
        message = JSON.parse(rawMessage) as Record<string, unknown>;
      } catch {
        return;
      }
      if (message.type === "hello_ack") {
        reconnectAttempt = 0;
        setConnectionState("connected");
        return;
      }
      if (message.type === "hello_error") {
        credentials = null;
        setConnectionState("error");
        currentSocket.close();
        return;
      }
      if (message.type !== "command" || typeof message.id !== "string") return;
      commandChain = commandChain
        .catch(() => undefined)
        .then(() => sendCommandResult(currentSocket, message as unknown as BrowserCommandMessage));
    };

    const connect = async () => {
      if (stopped) return;
      setConnectionState("connecting");
      try {
        credentials ||= await pairDesktopBrowser();
        if (stopped) return;
        const currentSocket = new WebSocket(browserSocketURL(), ["lazymind.browser.v1"]);
        socket = currentSocket;
        currentSocket.addEventListener("open", () => {
          currentSocket.send(JSON.stringify({
            type: "hello",
            protocol_version: PROTOCOL_VERSION,
            device_id: credentials?.device_id,
            device_token: credentials?.device_token,
          }));
        });
        currentSocket.addEventListener("message", (event) => {
          handleMessage(currentSocket, String(event.data || ""));
        });
        currentSocket.addEventListener("close", () => {
          if (socket !== currentSocket) return;
          socket = null;
          if (!stopped) {
            setConnectionState("connecting");
            scheduleReconnect();
          }
        });
        currentSocket.addEventListener("error", () => {
          if (!stopped) setConnectionState("error");
        });
      } catch {
        if (!stopped) {
          setConnectionState("error");
          scheduleReconnect();
        }
      }
    };

    void connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [enabled]);

  return connectionState;
}

export default function DesktopEmbeddedBrowser({
  onVisibilityChange,
}: DesktopEmbeddedBrowserProps) {
  const { t } = useTranslation();
  const enabled = isDesktopRuntime() && hasDesktopEmbeddedBrowser();
  const connectionState = useDesktopBrowserGateway(enabled);
  const [browserState, setBrowserState] = useState<DesktopEmbeddedBrowserState>(EMPTY_STATE);
  const [panelWidth, setPanelWidth] = useState(initialPanelWidth);
  const [address, setAddress] = useState("");
  const [dragging, setDragging] = useState(false);
  const viewSlotRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const dragCleanupRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    void embeddedBrowserState().then((state) => {
      if (active && state) setBrowserState(state);
    });
    const unsubscribe = onEmbeddedBrowserState((state) => {
      if (active) setBrowserState(state);
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [enabled]);

  useEffect(() => {
    onVisibilityChange?.(enabled && browserState.open);
    return () => onVisibilityChange?.(false);
  }, [browserState.open, enabled, onVisibilityChange]);

  useEffect(() => {
    if (!browserState.loading || document.activeElement !== document.querySelector(".desktop-browser-address")) {
      setAddress(browserState.url || "");
    }
  }, [browserState.loading, browserState.url]);

  const syncBounds = useCallback(() => {
    const slot = viewSlotRef.current;
    if (!enabled || !browserState.open || !slot || dragging) {
      void setEmbeddedBrowserBounds({ visible: false });
      return;
    }
    const rect = slot.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) {
      void setEmbeddedBrowserBounds({ visible: false });
      return;
    }
    void setEmbeddedBrowserBounds({
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      visible: true,
    });
  }, [browserState.open, dragging, enabled]);

  useEffect(() => {
    if (!enabled || !browserState.open) return undefined;
    const frame = window.requestAnimationFrame(syncBounds);
    const observer = new ResizeObserver(syncBounds);
    if (viewSlotRef.current) observer.observe(viewSlotRef.current);
    window.addEventListener("resize", syncBounds);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", syncBounds);
      void setEmbeddedBrowserBounds({ visible: false });
    };
  }, [browserState.open, enabled, syncBounds]);

  const invoke = useCallback(async (
    action: DesktopEmbeddedBrowserAction,
    payload: Record<string, unknown> = {},
  ) => {
    if (!browserState.session_id) return;
    await embeddedBrowserCommand(action, {
      session_id: browserState.session_id,
      ...payload,
    });
  }, [browserState.session_id]);

  const onAddressSubmit = (event: FormEvent) => {
    event.preventDefault();
    let url = address.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
    setAddress(url);
    void invoke("navigate", { url, allow_private_network: true });
  };

  const onResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragCleanupRef.current();
    dragRef.current = { startX: event.clientX, startWidth: panelWidth };
    setDragging(true);
    void setEmbeddedBrowserBounds({ visible: false });
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const onMove = (moveEvent: MouseEvent) => {
      if (!dragRef.current) return;
      const next = dragRef.current.startWidth + dragRef.current.startX - moveEvent.clientX;
      setPanelWidth(Math.max(MIN_PANEL_WIDTH, Math.min(maximumPanelWidth(), next)));
    };
    const cleanup = () => {
      dragRef.current = null;
      setDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    const onUp = () => cleanup();
    dragCleanupRef.current = cleanup;
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  useEffect(() => () => dragCleanupRef.current(), []);

  useEffect(() => {
    try { localStorage.setItem(PANEL_WIDTH_STORAGE_KEY, String(Math.round(panelWidth))); } catch {}
  }, [panelWidth]);

  if (!enabled || !browserState.open) return null;

  return (
    <aside
      className={`desktop-browser-panel${dragging ? " desktop-browser-panel--dragging" : ""}`}
      style={{ width: panelWidth, minWidth: panelWidth }}
      aria-label={t("chat.desktopBrowserTitle")}
    >
      <div
        className="desktop-browser-resize-handle"
        onMouseDown={onResizeStart}
        title={t("chat.desktopBrowserResize")}
      />
      <div className="desktop-browser-toolbar">
        <div className="desktop-browser-nav">
          <button
            type="button"
            disabled={!browserState.can_go_back || browserState.loading}
            onClick={() => void invoke("back")}
            aria-label={t("chat.desktopBrowserBack")}
          >
            &#8592;
          </button>
          <button
            type="button"
            disabled={!browserState.can_go_forward || browserState.loading}
            onClick={() => void invoke("forward")}
            aria-label={t("chat.desktopBrowserForward")}
          >
            &#8594;
          </button>
          <button
            type="button"
            disabled={browserState.loading}
            onClick={() => void invoke("reload")}
            aria-label={t("chat.desktopBrowserReload")}
          >
            &#8635;
          </button>
        </div>
        <form onSubmit={onAddressSubmit} className="desktop-browser-address-form">
          <span
            className={`desktop-browser-connection desktop-browser-connection--${connectionState}`}
            title={t(`chat.desktopBrowserConnection.${connectionState}`)}
          />
          <input
            className="desktop-browser-address"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            aria-label={t("chat.desktopBrowserAddress")}
            spellCheck={false}
          />
        </form>
        <button
          type="button"
          className="desktop-browser-close"
          onClick={() => void invoke("close")}
          aria-label={t("chat.desktopBrowserClose")}
        >
          &#215;
        </button>
      </div>
      <div className="desktop-browser-meta" title={browserState.title || browserState.url}>
        <span>{browserState.loading ? t("chat.desktopBrowserLoading") : (browserState.title || t("chat.desktopBrowserTitle"))}</span>
        {browserState.error && <span className="desktop-browser-error">{browserState.error}</span>}
      </div>
      <div ref={viewSlotRef} className="desktop-browser-view-slot" />
    </aside>
  );
}
