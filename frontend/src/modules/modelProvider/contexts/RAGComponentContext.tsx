import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { isLocalLikeRuntimeMode, getRuntimeMode } from "@/runtime/mode";
import { getPythonComponents } from "../api/systemDependencies";

type Availability = "checking" | "ready" | "missing" | "error";
const RAGComponentContext = createContext<{ availability: Availability; refresh: () => void }>({
  availability: "ready", refresh: () => {},
});

export function RAGComponentProvider({ children }: { children: ReactNode }) {
  const [availability, setAvailability] = useState<Availability>("checking");
  const requestId = useRef(0);
  const { pathname } = useLocation();
  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const items = await getPythonComponents();
      if (id === requestId.current) {
        setAvailability(items.some(item => item.id === "rag" && !item.active) ? "missing" : "ready");
      }
    } catch {
      if (id === requestId.current) {
        setAvailability(isLocalLikeRuntimeMode(getRuntimeMode()) ? "error" : "ready");
      }
    }
  }, []);
  useEffect(() => {
    void refresh();
    window.addEventListener("focus", refresh);
    return () => {
      ++requestId.current;
      window.removeEventListener("focus", refresh);
    };
  }, [refresh, pathname]);
  return <RAGComponentContext.Provider value={{ availability, refresh }}>{children}</RAGComponentContext.Provider>;
}

export function useRAGComponent() {
  return useContext(RAGComponentContext);
}
