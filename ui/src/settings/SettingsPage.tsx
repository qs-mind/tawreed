import { useState, type FormEvent, type ReactNode } from "react";
import { AccountLine } from "../account/Account";
import { ApiError, explain, type Connection, type Provider } from "../api/client";
import { useSettings } from "../app/settings";
import { Alert, button, Empty, field, link, Page, PageTitle, SectionLabel, Skeleton, SkeletonRows } from "../app/ui";
import type { Key } from "../i18n";
import {
  PROVIDERS,
  useAddConnection,
  useCheckModel,
  useCodex,
  useCodexSignIn,
  useConnections,
  useForgetRule,
  useModels,
  useRemoveConnection,
  useRules,
} from "./queries";

export function SettingsPage() {
  const { t, language, theme, change } = useSettings();

  return (
    <Page className="gap-10">
      <div className="flex flex-col gap-4">
        <PageTitle>{t("settings.title")}</PageTitle>
        <div className="flex flex-col">
          <Row label={t("settings.account")}>
            <AccountLine />
          </Row>
          <Row label={t("settings.language")}>
            <Choice
              label={t("settings.language")}
              value={language}
              options={[
                { value: "en", label: "English", lang: "en" },
                { value: "ar", label: "العربية", lang: "ar" },
              ]}
              onChange={(value) => void change({ language: value })}
            />
          </Row>
          <Row label={t("settings.theme")}>
            <Choice
              label={t("settings.theme")}
              value={theme}
              options={(["system", "light", "dark"] as const).map((value) => ({ value, label: t(`theme.${value}` as Key) }))}
              onChange={(value) => void change({ theme: value })}
            />
          </Row>
          <Row label={t("settings.ai")}>
            <TawreedsAI />
          </Row>
        </div>
      </div>

      <section className="flex flex-col">
        <SectionLabel>{t("settings.connections")}</SectionLabel>
        <Connections />
      </section>

      <section className="flex flex-col">
        <SectionLabel>{t("settings.rules")}</SectionLabel>
        <Rules />
      </section>
    </Page>
  );
}

function Rules() {
  const { t } = useSettings();
  const rules = useRules();
  const forget = useForgetRule();
  if (rules.isPending) return <SkeletonRows rows={2} />;
  if (rules.isError) return <Alert onRetry={() => void rules.refetch()}>{explain(rules.error, t)}</Alert>;
  if (rules.data.length === 0) return <Empty>{t("settings.noRules")}</Empty>;
  return (
    <ul className="flex flex-col">
      {rules.data.map((rule) => (
        <li key={rule.id} className="flex items-center gap-4 border-t border-line-soft py-3 first:border-t-0">
          <span className="flex-1 [unicode-bidi:plaintext]">{rule.text}</span>
          <button
            type="button"
            disabled={forget.isPending}
            onClick={() => forget.mutate(rule.id)}
            className={`shrink-0 text-sm ${link}`}
          >
            {t("rules.remove")}
          </button>
        </li>
      ))}
    </ul>
  );
}

/** A setting: its name, and the control that changes it. Side by side, or stacked in a narrow window. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-t border-line-soft py-3 first:border-t-0 sm:flex-row sm:items-center sm:gap-4">
      <span className="shrink-0 font-semibold sm:w-40">{label}</span>
      {children}
    </div>
  );
}

/** A small segmented choice: one pressed button per option. */
function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; lang?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex gap-0.5 self-start rounded-lg bg-subtle p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          lang={option.lang}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
          className={`h-8 rounded-md px-3.5 transition-[color,background-color,box-shadow] duration-150 pointer-coarse:h-10 ${option.value === value ? "bg-page text-ink shadow-[0_1px_2px_var(--shadow-far)]" : "text-ink-2 hover:text-ink"}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function connectionName(connection: Connection, t: ReturnType<typeof useSettings>["t"]): string {
  return connection.provider === "openai_compatible" ? connection.label : t(`provider.${connection.provider}` as Key);
}

/** Which checked model Tawreed works with. Only models that passed their check are offered. */
function TawreedsAI() {
  const { t, ai, change } = useSettings();
  const connections = useConnections();
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  if (connections.isPending) return <Skeleton className="h-9 w-full max-w-md" />;
  const choices = (connections.data ?? []).flatMap((connection) =>
    Object.entries(connection.checks)
      .filter(([, check]) => check.ok)
      .map(([model]) => ({ connection_id: connection.id, model, label: `${model} · ${connectionName(connection, t)}` })),
  );

  if (choices.length === 0) return <span className="text-ink-2">{t("settings.aiNone")}</span>;
  const current = ai ? JSON.stringify([ai.connection_id, ai.model]) : "";
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <select
        aria-label={t("settings.ai")}
        value={current}
        disabled={saving}
        onChange={async (event) => {
          const [connection_id, model] = JSON.parse(event.target.value) as [string, string];
          setSaving(true);
          setError(await change({ ai: { connection_id, model } }));
          setSaving(false);
        }}
        className={`${field} w-full`}
      >
        <option value="" disabled>
          {t("settings.aiChoose")}
        </option>
        {choices.map((choice) => (
          <option key={`${choice.connection_id}|${choice.model}`} value={JSON.stringify([choice.connection_id, choice.model])}>
            {choice.label}
          </option>
        ))}
      </select>
      {error ? <Alert>{explain(error, t)}</Alert> : null}
    </div>
  );
}

function Connections() {
  const { t } = useSettings();
  const connections = useConnections();
  return (
    <div className="flex flex-col gap-3">
      {connections.isError && <Alert onRetry={() => void connections.refetch()}>{explain(connections.error, t)}</Alert>}
      {connections.isPending && <Skeleton className="h-28 w-full rounded-xl" />}
      {connections.data?.length === 0 && <Empty>{t("settings.noConnections")}</Empty>}
      {connections.data?.map((connection) => <ConnectionRow key={connection.id} connection={connection} />)}
      <AddConnection />
      <p className="text-sm text-ink-2">{t("settings.keysNote")}</p>
    </div>
  );
}

function ConnectionRow({ connection }: { connection: Connection }) {
  const { t } = useSettings();
  const models = useModels(connection.id);
  const check = useCheckModel(connection.id);
  const remove = useRemoveConnection();
  const [model, setModel] = useState("");
  const [removing, setRemoving] = useState(false);
  const result = model ? connection.checks[model] : undefined;
  const name = connectionName(connection, t);

  return (
    <section aria-label={name} className="flex flex-col gap-3 rounded-xl border border-line p-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="font-semibold">{name}</span>
        <span className="order-last w-full text-sm text-ink-2 sm:order-none sm:w-auto sm:min-w-0 sm:flex-1">
          {connection.provider === "codex" ? t("connection.codex") : t("connection.key", { hint: connection.key_hint })}
        </span>
        {!removing && (
          <button type="button" onClick={() => setRemoving(true)} className={`${button("quiet", "sm")} ms-auto sm:ms-0`}>
            {t("connection.remove")}
          </button>
        )}
      </div>
      {removing && (
        <div role="group" aria-label={t("connection.removeConfirm", { name })} className="flex flex-wrap items-center gap-3 rounded-lg bg-subtle px-3 py-2.5 text-sm animate-enter">
          <span className="min-w-0 flex-1">{t("connection.removeConfirm", { name })}</span>
          <button
            type="button"
            onClick={() => remove.mutate(connection.id)}
            disabled={remove.isPending}
            className={button("danger", "sm")}
          >
            {t("connection.remove")}
          </button>
          <button type="button" autoFocus onClick={() => setRemoving(false)} className={button("quiet", "sm")}>
            {t("ui.cancel")}
          </button>
        </div>
      )}
      <div className="flex items-center gap-2">
        {models.data && models.data.length > 0 ? (
          <select aria-label={t("connection.model")} value={model} onChange={(e) => setModel(e.target.value)} className={`${field} min-w-0 flex-1`}>
            <option value="">{t("connection.chooseModel")}</option>
            {models.data.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        ) : (
          <input
            aria-label={t("connection.model")}
            value={model}
            dir="ltr"
            onChange={(e) => setModel(e.target.value.trim())}
            placeholder={models.isPending ? t("connection.loadingModels") : t("connection.modelName")}
            className={`${field} min-w-0 flex-1`}
          />
        )}
        <button type="button" disabled={!model || check.isPending} onClick={() => check.mutate(model)} className={button("secondary")}>
          {check.isPending ? t("connection.checking") : t("connection.check")}
        </button>
      </div>
      {(check.isPending || models.isError || check.isError || remove.isError || (result && !check.isPending)) && (
        <div className="flex flex-col gap-1 text-sm">
          {check.isPending && <p className="text-ink-2">{t("connection.checkingNote")}</p>}
          {(models.isError || check.isError || remove.isError) && (
            <Alert>{explain(models.error ?? check.error ?? remove.error, t)}</Alert>
          )}
          {result && !check.isPending && (
            <p className={`flex items-start gap-1.5 ${result.ok ? "text-ink-2" : "text-danger"}`}>
              <span className={`mt-[7px] size-1.5 shrink-0 rounded-full ${result.ok ? "bg-ink" : "bg-danger"}`} aria-hidden="true" />
              {result.ok
                ? `${t("check.works")} ${result.sees_images ? t("check.sees") : t("check.blind")}`
                : explain(new ApiError(result.problem ?? "unknown"), t)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function AddConnection() {
  const { t } = useSettings();
  const add = useAddConnection();
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [address, setAddress] = useState("");
  const needsAddress = provider === "openai_compatible";
  const isCodex = provider === "codex";
  const codex = useCodex(isCodex);

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate(
      { provider, api_key: key.trim(), base_url: needsAddress ? address.trim() : null },
      {
        onSuccess: () => {
          setKey("");
          setAddress("");
          setShowKey(false);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-xl border border-dashed border-line-strong p-4">
      <h3 className="font-heading font-semibold">{t("add.title")}</h3>
      <fieldset className="flex flex-wrap gap-1.5">
        <legend className="sr-only">{t("add.service")}</legend>
        {PROVIDERS.map((id) => (
          <label
            key={id}
            className="flex h-9 cursor-pointer items-center rounded-lg border border-line-strong px-3 text-ink-2 transition-colors duration-150 hover:border-ink/35 hover:text-ink has-checked:border-ink has-checked:bg-subtle has-checked:text-ink has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ink pointer-coarse:h-11"
          >
            <input
              type="radio"
              name="provider"
              value={id}
              checked={provider === id}
              onChange={() => setProvider(id)}
              className="sr-only"
            />
            {t(`provider.${id}` as Key)}
          </label>
        ))}
      </fieldset>
      {isCodex && <CodexState state={codex.data} />}
      {/* Keys read left to right in either language, so the field and its eye button do too. */}
      {!isCodex && (
        <div className="relative flex" dir="ltr">
          <input
            aria-label={t("add.key")}
            type={showKey ? "text" : "password"}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={t("add.key")}
            autoComplete="off"
            spellCheck={false}
            className={`${field} min-w-0 flex-1 pe-10`}
          />
          <button
            type="button"
            aria-label={t("add.show")}
            aria-pressed={showKey}
            onClick={() => setShowKey(!showKey)}
            className="absolute inset-y-0 end-0 flex w-10 items-center justify-center rounded-e-lg text-ink-2 transition-colors hover:text-ink"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
              <circle cx="12" cy="12" r="3" />
              {showKey && <path d="M4 4l16 16" />}
            </svg>
          </button>
        </div>
      )}
      {needsAddress && (
        <input
          aria-label={t("add.address")}
          value={address}
          dir="ltr"
          onChange={(e) => setAddress(e.target.value)}
          placeholder="https://api.example.com/v1"
          className={field}
        />
      )}
      {add.isError && <Alert>{explain(add.error, t)}</Alert>}
      <button
        type="submit"
        disabled={(isCodex ? !codex.data?.signed_in : !key.trim()) || (needsAddress && !address.trim()) || add.isPending}
        className={`${button("primary")} self-start font-semibold`}
      >
        {add.isPending ? t("add.checking") : t("add.submit")}
      </button>
    </form>
  );
}

/** Where Codex stands on this computer, and its own sign-in when it isn't signed in. */
function CodexState({ state }: { state: { installed: boolean; version: string | null; signed_in: boolean } | undefined }) {
  const { t } = useSettings();
  const signIn = useCodexSignIn();
  if (!state) return <p className="text-sm text-ink-2">{t("codex.looking")}</p>;
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      {!state.installed && <p className="text-amber">{t("codex.missing")}</p>}
      {state.installed && state.signed_in && <p>{t("codex.signedIn", { version: state.version ?? "" })}</p>}
      {state.installed && !state.signed_in && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-amber">{t("codex.signedOut", { version: state.version ?? "" })}</p>
          <button type="button" disabled={signIn.isPending} onClick={() => signIn.mutate()} className={button("secondary", "sm")}>
            {t("codex.signIn")}
          </button>
        </div>
      )}
      {state.installed && !state.signed_in && <p className="text-ink-2">{t("codex.signInNote")}</p>}
      <p className="text-ink-2">{t("codex.lockdown")}</p>
      {signIn.isError && <Alert>{explain(signIn.error, t)}</Alert>}
    </div>
  );
}
