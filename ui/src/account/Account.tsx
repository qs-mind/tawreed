import { explain, type Account } from "../api/client";
import { useSettings } from "../app/settings";
import { Alert, button, Skeleton } from "../app/ui";
import { useAccount, useSignOut } from "./queries";

function day(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "long" }).format(new Date(iso));
}

/** The plan as the account service names it; "Free" when it names none. */
function plan(account: Account, t: ReturnType<typeof useSettings>["t"]): string {
  const name = account.plan?.trim();
  return !name || name.toLowerCase() === "free" ? t("account.free") : name;
}

/** Settings → Account: who is signed in, the plan, and Sign out. */
export function AccountLine() {
  const { t, locale } = useSettings();
  const account = useAccount();
  const signOut = useSignOut();
  if (account.isPending) return <Skeleton className="h-10 w-full" />;
  if (account.isError) return <Alert onRetry={() => void account.refetch()}>{explain(account.error, t)}</Alert>;
  const a = account.data;

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="[overflow-wrap:anywhere]">
          {a.name ? `${a.name} · ` : ""}
          <span dir="ltr">{a.email}</span>
        </span>
        <span className="text-sm text-ink-2">{t("account.plan", { plan: plan(a, t) })}</span>
        {a.state === "offline" && a.lease_ends_at && (
          <span className="text-sm text-ink-2">{t("account.offline", { date: day(a.lease_ends_at, locale) })}</span>
        )}
        {a.state === "expired" && <span className="text-sm text-amber">{t("error.read_only")}</span>}
      </div>
      <button
        type="button"
        disabled={signOut.isPending}
        onClick={() => signOut.mutate()}
        className={`shrink-0 self-start sm:self-auto ${button("secondary", "sm")}`}
      >
        {t("account.signOut")}
      </button>
      {signOut.isError && <Alert>{explain(signOut.error, t)}</Alert>}
    </div>
  );
}

/** A line under the header once the offline lease is over: Tawreed is read-only, and nothing is lost. */
export function ReadOnly({ account }: { account: Account }) {
  const { t, locale } = useSettings();
  const again = useAccount();
  if (account.state !== "expired" || !account.lease_ends_at) return null;
  return (
    <div className="shrink-0 border-b border-amber-line bg-amber-soft">
      <div className="mx-auto flex w-full max-w-[880px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 sm:px-6">
        <span role="status" className="min-w-0 flex-1 text-amber">
          {t("account.expired", { date: day(account.lease_ends_at, locale) })}
        </span>
        <button
          type="button"
          disabled={again.isFetching}
          onClick={() => void again.refetch()}
          className={button("secondary", "sm")}
        >
          {t("ui.retry")}
        </button>
      </div>
    </div>
  );
}
