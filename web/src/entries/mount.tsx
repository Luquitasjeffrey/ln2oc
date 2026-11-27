import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";
import { DocsLayout, SiteLayout, type PageKey } from "../components/Layout";

export function mount(current: PageKey, Page: ComponentType) {
  createRoot(document.getElementById("root")!).render(
    current === "index" ? (
      <SiteLayout>
        <Page />
      </SiteLayout>
    ) : (
      <DocsLayout current={current}>
        <Page />
      </DocsLayout>
    ),
  );
}
