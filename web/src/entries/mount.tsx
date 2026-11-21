import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";
import { Layout, type PageKey } from "../components/Layout";

export function mount(current: PageKey, Page: ComponentType) {
  createRoot(document.getElementById("root")!).render(
    <Layout current={current}>
      <Page />
    </Layout>,
  );
}
