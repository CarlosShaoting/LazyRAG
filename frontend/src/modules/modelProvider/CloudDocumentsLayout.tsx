import { Outlet } from "react-router-dom";
import { RAGComponentProvider } from "./contexts/RAGComponentContext";
import "./index.scss";

export default function CloudDocumentsLayout() {
  return (
    <RAGComponentProvider>
      <main className="model-provider-page model-provider-cloud-doc-layout">
        <div className="model-provider-layout-frame">
          <Outlet />
        </div>
      </main>
    </RAGComponentProvider>
  );
}
