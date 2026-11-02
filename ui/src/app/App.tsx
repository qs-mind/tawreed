import { useState, type ReactNode } from "react";
import { About } from "../about/About";
import { ReadOnly } from "../account/Account";
import { useAccount } from "../account/queries";
import { SignIn } from "../account/SignIn";
import { explain } from "../api/client";
import { History } from "../history/History";
import { Home } from "../home/Home";
import type { Key } from "../i18n";
import { SettingsPage } from "../settings/SettingsPage";
import { Logo } from "./Logo";
import { useSettings } from "./settings";
import { Alert, Page, Skeleton } from "./ui";
import { Update } from "./Update";

type Tab = "home" | "history" | "settings" | "about";
const TABS: Tab[] = ["home", "history", "settings", "about"];

/** Signed in to QS Mind first; then Tawreed's four tabs. */
export function App() {
  const { t } = useSettings();
  const account = useAccount();
  // A later check that fails keeps the last answer: only a first answer that never came stops the app.
  if (!account.data) {
    return (
      <Page>
        {account.isError ? (
          <Alert onRetry={() => void account.refetch()}>{explain(account.error, t)}</Alert>
        ) : (
          <Skeleton className="h-24 w-full" />
        )}
      </Page>
    );
  }
  if (account.data.state === "signed_out") return <SignIn account={account.data} />;
  return <Tabs readOnly={<ReadOnly account={account.data} />} />;
}

function Tabs({ readOnly }: { readOnly: ReactNode }) {
  const { t, language, change } = useSettings();
  const [tab, setTab] = useState<Tab>("home");
  const [projectId, setProjectId] = useState<string | null>(null);

  const open = (id: string) => {
    setProjectId(id);
    setTab("home");
  };

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 border-b border-line bg-page">
        {/* The same column as the screens below, so the logo lines up with their titles. In a narrow window the
            tabs take a row of their own under the logo, so none is ever cut off. */}
        <div className="mx-auto flex w-full max-w-[880px] flex-wrap items-center gap-x-8 px-4 sm:h-[52px] sm:flex-nowrap sm:px-6">
          <span className="flex h-12 shrink-0 items-center gap-2 text-[19px] font-semibold sm:h-auto">
            <Logo size={26} />
            {t("app.name")}
          </span>
          <nav
            aria-label={t("tabs.label")}
            className="order-last flex h-11 w-full justify-between sm:order-none sm:h-full sm:w-auto sm:justify-start sm:gap-6"
          >
            {TABS.map((name) => (
              <button
                key={name}
                type="button"
                aria-current={tab === name ? "page" : undefined}
                onClick={() => setTab(name)}
                className={`h-full border-b-2 px-1 transition-colors duration-150 focus-visible:outline-offset-[-2px] ${tab === name ? "border-ink text-ink" : "border-transparent text-ink-2 hover:border-line-strong hover:text-ink"}`}
              >
                {t(`tab.${name}` as Key)}
              </button>
            ))}
          </nav>
          <button
            type="button"
            lang={language === "en" ? "ar" : "en"}
            onClick={() => change({ language: language === "en" ? "ar" : "en" })}
            className="ms-auto h-9 shrink-0 rounded-lg px-2 text-ink-2 transition-colors duration-150 hover:bg-subtle hover:text-ink"
          >
            {t("language.other")}
          </button>
        </div>
      </header>
      <Update />
      {readOnly}
      <main className="min-h-0 flex-1 overflow-y-auto">
        {tab === "home" && (
          <Home
            projectId={projectId}
            onOpen={open}
            onClose={() => setProjectId(null)}
            onOpenSettings={() => setTab("settings")}
          />
        )}
        {tab === "history" && <History onOpen={open} />}
        {tab === "settings" && <SettingsPage />}
        {tab === "about" && <About />}
      </main>
    </div>
  );
}
