import { ApiError, explain, type Account } from "../api/client";
import { Logo } from "../app/Logo";
import { useSettings } from "../app/settings";
import { Alert, button, Icon, link } from "../app/ui";
import { useCancelSignIn, useSignIn } from "./queries";

/** The one screen before Home while no one is signed in: sign in with QS Mind, in the browser or with a code. */
export function SignIn({ account }: { account: Account }) {
  const { t, language, change } = useSettings();
  const start = useSignIn();
  const cancel = useCancelSignIn();
  const pending = account.pending;
  const problem = start.error ?? (account.problem ? new ApiError(account.problem) : null);

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex shrink-0 justify-end px-4 pt-3 sm:px-6">
        <button
          type="button"
          lang={language === "en" ? "ar" : "en"}
          onClick={() => change({ language: language === "en" ? "ar" : "en" })}
          className="h-9 rounded-lg px-2 text-ink-2 transition-colors duration-150 hover:bg-subtle hover:text-ink"
        >
          {t("language.other")}
        </button>
      </div>
      <main className="mx-auto flex w-full max-w-[440px] flex-1 flex-col justify-center gap-8 px-4 pb-16 sm:px-6">
        <div className="flex flex-col items-start gap-4">
          <Logo size={48} />
          <h1 className="font-heading text-title font-light text-balance">{t("signin.title")}</h1>
          <p className="text-ink-2">{t("signin.lead")}</p>
        </div>

        {pending ? (
          <section aria-live="polite" className="flex flex-col items-start gap-3">
            {pending.method === "browser" ? (
              <>
                <p role="status" className="font-semibold">{t("signin.waiting")}</p>
                <p className="text-sm text-ink-2">{t("signin.noBrowser")}</p>
                <Address url={pending.url} />
              </>
            ) : (
              <>
                <p className="text-ink-2">{t("signin.codeLead")}</p>
                <Address url={pending.url} />
                <p dir="ltr" className="font-heading text-3xl font-semibold tracking-[0.12em] select-all">{pending.user_code}</p>
                <p role="status" className="text-ink-2">{t("signin.codeWaiting")}</p>
              </>
            )}
            <button type="button" onClick={() => cancel.mutate()} disabled={cancel.isPending} className={button("secondary")}>
              {t("ui.cancel")}
            </button>
          </section>
        ) : (
          <section className="flex flex-col items-start gap-3">
            <button
              type="button"
              disabled={start.isPending}
              onClick={() => start.mutate({ language, code: false })}
              className={`w-full ${button("primary")}`}
            >
              {t("signin.button")}
            </button>
            <button
              type="button"
              disabled={start.isPending}
              onClick={() => start.mutate({ language, code: true })}
              className={`text-sm ${link}`}
            >
              {t("signin.withCode")}
            </button>
            {problem && <Alert>{explain(problem, t)}</Alert>}
          </section>
        )}

        <ul className="flex flex-col gap-2 border-t border-line pt-5 text-sm text-ink-2">
          <li className="flex gap-2">
            <Icon name="check" />
            <span>{t("signin.account")}</span>
          </li>
          <li className="flex gap-2">
            <Icon name="check" />
            <span>{t("signin.boqs")}</span>
          </li>
        </ul>
      </main>
    </div>
  );
}

/** An address to copy, should the browser not have opened: the whole of it, selected with one click. */
function Address({ url }: { url: string }) {
  return (
    <p dir="ltr" className="w-full rounded-lg border border-line bg-soft px-3 py-2 text-sm [overflow-wrap:anywhere] select-all">
      {url}
    </p>
  );
}
