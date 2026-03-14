import { BrowserRouter, Route, Routes } from "react-router-dom";

import { NavShell } from "./components/nav-shell";
import { I18nProvider } from "./lib/i18n";
import { InboxPage } from "./pages/inbox-page";
import { KnowledgePage } from "./pages/knowledge-page";
import { RunsPage } from "./pages/runs-page";
import { SettingsPage } from "./pages/settings-page";

export default function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <NavShell>
          <Routes>
            <Route path="/" element={<InboxPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </NavShell>
      </BrowserRouter>
    </I18nProvider>
  );
}
