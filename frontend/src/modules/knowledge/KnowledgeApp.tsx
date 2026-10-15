import { RAGComponentNotice } from "@/modules/modelProvider/components/PythonComponentDependencies";
import { useRAGComponent } from "@/modules/modelProvider/contexts/RAGComponentContext";
import { Spin } from "antd";
import { Outlet } from "react-router-dom";
import KnowledgeLayout from "./layout";
import "./style.css";

export default function KnowledgeApp() {
  const { availability } = useRAGComponent();

  return (
    <KnowledgeLayout>
      <RAGComponentNotice />
      {availability === "checking" ? (
        <Spin style={{ display: "flex", justifyContent: "center", marginTop: 48 }} />
      ) : availability === "ready" ? (
        <Outlet />
      ) : null}
    </KnowledgeLayout>
  );
}
