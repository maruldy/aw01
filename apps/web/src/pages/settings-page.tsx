import { useEffect, useState } from "react";

import {
  getGitHubRepositories,
  getProfiles,
  getSchedulerJobs,
  startGitHubConnection,
  updateConnectorConfig,
  updateSubscriptions,
  validateProfile
} from "../lib/api";
import { useTranslation } from "../lib/i18n";
import type { ConnectorProfile, GitHubRepository } from "../lib/types";

export function SettingsPage() {
  const { t } = useTranslation();
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [validation, setValidation] = useState<Record<string, string>>({});
  const [draftConfigValues, setDraftConfigValues] = useState<Record<string, Record<string, string>>>({});
  const [draftSelections, setDraftSelections] = useState<Record<string, string[]>>({});
  const [githubRepositories, setGitHubRepositories] = useState<GitHubRepository[]>([]);
  const [isConnectingGitHub, setIsConnectingGitHub] = useState(false);
  const [jobs, setJobs] = useState<Array<Record<string, string>>>([]);

  async function applyProfiles(nextProfiles: ConnectorProfile[]) {
    setProfiles(nextProfiles);
    setDraftConfigValues(
      Object.fromEntries(
        nextProfiles.map((profile) => [
          profile.source,
          Object.fromEntries(
            profile.config_fields.map((field) => [field.key, field.value ?? ""])
          )
        ])
      )
    );
    setDraftSelections(
      Object.fromEntries(
        nextProfiles.map((profile) => [profile.source, profile.selected_event_keys])
      )
    );

    const githubProfile = nextProfiles.find((profile) => profile.source === "github");
    if (!githubProfile || githubProfile.missing_fields.includes("GITHUB_TOKEN")) {
      setGitHubRepositories([]);
      return;
    }

    try {
      const repositoriesPayload = await getGitHubRepositories();
      setGitHubRepositories(repositoriesPayload.repositories);
    } catch {
      setGitHubRepositories([]);
    }
  }

  useEffect(() => {
    async function load() {
      const params = new URLSearchParams(window.location.search);
      const githubStatus = params.get("github");
      const githubMessage = params.get("github_message");
      if (githubStatus === "connected") {
        setValidation((previous) => ({
          ...previous,
          github: githubMessage ?? t("settings.githubConnected")
        }));
      } else if (githubStatus === "error") {
        setValidation((previous) => ({
          ...previous,
          github: githubMessage ?? t("settings.githubFailed")
        }));
      }
      if (githubStatus) {
        params.delete("github");
        params.delete("github_message");
        const nextSearch = params.toString();
        const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}${window.location.hash}`;
        window.history.replaceState({}, "", nextUrl);
      }

      const [profilePayload, jobsPayload] = await Promise.all([getProfiles(), getSchedulerJobs()]);
      await applyProfiles(profilePayload.profiles);
      setJobs(jobsPayload.jobs);
    }
    void load();
  }, []);

  async function handleValidate(source: string) {
    const result = await validateProfile(source);
    await applyProfiles(
      profiles.map((profile) => (profile.source === source ? result : profile))
    );
    setValidation((previous) => ({
      ...previous,
      [source]: result.ok ? t("settings.connectedStatus") : t("settings.checkedSafely")
    }));
  }

  async function handleSaveConfig(source: string) {
    const result = await updateConnectorConfig(source, draftConfigValues[source] ?? {});
    await applyProfiles(
      profiles.map((profile) => (profile.source === source ? result : profile))
    );
    setValidation((previous) => ({
      ...previous,
      [source]: source === "github" ? t("settings.repoSaved") : t("settings.configSaved")
    }));
  }

  async function handleSaveSubscriptions(source: string) {
    const result = await updateSubscriptions(source, draftSelections[source] ?? []);
    setProfiles((previous) => previous.map((profile) => (profile.source === source ? result : profile)));
    setValidation((previous) => ({
      ...previous,
      [source]: t("settings.subscriptionSaved")
    }));
  }

  function toggleSubscription(source: string, key: string) {
    setDraftSelections((previous) => {
      const current = new Set(previous[source] ?? []);
      if (current.has(key)) {
        current.delete(key);
      } else {
        current.add(key);
      }
      return {
        ...previous,
        [source]: [...current]
      };
    });
  }

  function updateConfigValue(source: string, key: string, value: string) {
    setDraftConfigValues((previous) => ({
      ...previous,
      [source]: {
        ...(previous[source] ?? {}),
        [key]: value
      }
    }));
  }

  async function handleConnectGitHub() {
    setIsConnectingGitHub(true);
    try {
      const payload = await startGitHubConnection(
        window.location.origin,
        window.location.pathname
      );
      window.location.assign(payload.authorization_url);
    } catch (error) {
      setValidation((previous) => ({
        ...previous,
        github:
          error instanceof Error ? error.message : t("settings.githubStartFailed")
      }));
      setIsConnectingGitHub(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="panel">
        <p className="eyebrow">{t("settings.eyebrow")}</p>
        <h1 className="panel-title">{t("settings.title")}</h1>
        <p className="mt-3 text-sm text-ink/70">
          {t("settings.subtitle")}
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="panel">
          <p className="eyebrow">{t("settings.profilesEyebrow")}</p>
          <div className="mt-5 space-y-3">
            {profiles.map((profile) => (
              <div key={profile.source} className="rounded-[22px] border border-black/5 bg-white/80 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-display text-xl">{profile.name}</p>
                    <p className="mt-1 text-sm text-ink/60">{profile.source} · {profile.mode}</p>
                    {profile.identity ? (
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-pine">
                        {t("settings.identity")}: {profile.identity}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleValidate(profile.source)}
                      className="rounded-[16px] bg-ocean px-4 py-2 text-sm font-semibold text-white"
                    >
                      {t("settings.validate")}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSaveSubscriptions(profile.source)}
                      className="rounded-[16px] bg-ink px-4 py-2 text-sm font-semibold text-white"
                    >
                      {t("settings.saveAlerts")}
                    </button>
                  </div>
                </div>
                <div className="mt-3 rounded-[18px] bg-canvas px-4 py-3">
                  <p className="text-sm text-ink/75">
                    {validation[profile.source] ?? profile.message}
                  </p>
                  {!profile.configured ? (
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-signal">
                      {t("settings.missing")}: {profile.missing_fields.join(", ")}
                    </p>
                  ) : (
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-pine">{t("settings.ready")}</p>
                  )}
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                  <div className="rounded-[18px] border border-black/5 bg-white/90 p-4 lg:col-span-2">
                    {profile.source === "github" ? (
                      <>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="eyebrow">{t("settings.browserConnection")}</p>
                            <p className="mt-2 text-sm text-ink/70">
                              {t("settings.browserConnectionDesc")}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={handleConnectGitHub}
                            disabled={isConnectingGitHub}
                            className="rounded-[16px] bg-signal px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-signal/60"
                          >
                            {isConnectingGitHub ? t("settings.redirecting") : profile.identity ? t("settings.reconnectGitHub") : t("settings.connectGitHub")}
                          </button>
                        </div>

                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          <div className="rounded-[18px] bg-canvas px-4 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-sm font-semibold text-ink">{t("settings.connectedAccount")}</span>
                              {profile.identity ? <span className="pill">{t("settings.connected")}</span> : null}
                            </div>
                            <p className="mt-3 text-sm text-ink/70">
                              {profile.identity ?? t("settings.noGitHubAccount")}
                            </p>
                          </div>

                          <label className="rounded-[18px] bg-canvas px-4 py-3">
                            <span className="text-sm font-semibold text-ink">{t("settings.scopedRepo")}</span>
                            <select
                              value={draftConfigValues[profile.source]?.github_repository ?? ""}
                              onChange={(event) => updateConfigValue(profile.source, "github_repository", event.target.value)}
                              disabled={githubRepositories.length === 0}
                              className="mt-3 w-full rounded-[14px] border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-signal disabled:bg-black/5"
                            >
                              <option value="">{t("settings.selectRepo")}</option>
                              {githubRepositories.map((repository) => (
                                <option key={repository.full_name} value={repository.full_name}>
                                  {repository.full_name}{repository.private ? ` ${t("settings.private")}` : ""}
                                </option>
                              ))}
                            </select>
                            <p className="mt-2 text-xs text-ink/55">
                              {githubRepositories.length > 0
                                ? t("settings.chooseRepo")
                                : t("settings.connectFirst")}
                            </p>
                          </label>
                        </div>

                        <div className="mt-4 flex justify-end">
                          <button
                            type="button"
                            onClick={() => handleSaveConfig(profile.source)}
                            disabled={!draftConfigValues[profile.source]?.github_repository}
                            className="rounded-[16px] bg-ink px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-ink/60"
                          >
                            {t("settings.saveRepo")}
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="eyebrow">{t("settings.connectionInputs")}</p>
                            <p className="mt-2 text-sm text-ink/70">
                              {t("settings.connectionInputsDesc")}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleSaveConfig(profile.source)}
                            className="rounded-[16px] bg-signal px-4 py-2 text-sm font-semibold text-white"
                          >
                            {t("settings.saveConfig")}
                          </button>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          {profile.config_fields.map((field) => (
                            <label key={field.key} className="rounded-[18px] bg-canvas px-4 py-3">
                              <div className="flex items-center justify-between gap-3">
                                <span className="text-sm font-semibold text-ink">{field.label}</span>
                                {field.sensitive && field.is_set ? <span className="pill">{t("settings.stored")}</span> : null}
                              </div>
                              <input
                                type={field.sensitive ? "password" : "text"}
                                value={draftConfigValues[profile.source]?.[field.key] ?? ""}
                                onChange={(event) => updateConfigValue(profile.source, field.key, event.target.value)}
                                placeholder={field.sensitive && field.is_set ? t("settings.keepCurrent") : field.placeholder}
                                className="mt-3 w-full rounded-[14px] border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-signal"
                              />
                              <p className="mt-2 text-xs text-ink/55">{field.help_text}</p>
                            </label>
                          ))}
                        </div>
                      </>
                    )}
                  </div>

                  {profile.webhook ? (
                    <div className="rounded-[18px] border border-black/5 bg-white/90 p-4 lg:col-span-2">
                      <p className="eyebrow">{t("settings.webhookIntake")}</p>
                      <div className="mt-3 rounded-[16px] bg-canvas px-4 py-3">
                        <p className="text-sm font-semibold text-ink">{t("settings.callbackUrl")}</p>
                        <p className="mt-2 break-all text-sm text-ink/70">
                          {profile.webhook.callback_url}
                        </p>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div className="rounded-[16px] bg-canvas px-4 py-3">
                          <p className="text-sm font-semibold text-ink">{t("settings.verification")}</p>
                          <p className="mt-2 text-sm text-ink/70">
                            {profile.webhook.verification_mode}
                          </p>
                          {profile.webhook.secret_env_key ? (
                            <p className="mt-2 text-xs uppercase tracking-[0.18em] text-pine">
                              {t("settings.secretEnv")}: {profile.webhook.secret_env_key}
                            </p>
                          ) : null}
                        </div>
                        <div className="rounded-[16px] bg-canvas px-4 py-3">
                          <p className="text-sm font-semibold text-ink">{t("settings.recommendedEvents")}</p>
                          <p className="mt-2 text-sm text-ink/70">
                            {profile.webhook.recommended_events.join(", ")}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 space-y-2">
                        {profile.webhook.setup_notes.map((note) => (
                          <div key={note} className="rounded-[16px] bg-canvas px-4 py-3 text-sm text-ink/70">
                            {note}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="rounded-[18px] border border-black/5 bg-white/90 p-4">
                    <p className="eyebrow">{t("settings.capabilityProbe")}</p>
                    <div className="mt-3 space-y-3">
                      {profile.capabilities.map((capability) => (
                        <div key={capability.key} className="rounded-[16px] bg-canvas px-3 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-ink">{capability.label}</p>
                            <span className="pill">{capability.status}</span>
                          </div>
                          <p className="mt-2 text-sm text-ink/65">{capability.detail}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[18px] border border-black/5 bg-white/90 p-4">
                    <p className="eyebrow">{t("settings.alertSubscriptions")}</p>
                    <p className="mt-3 text-sm leading-7 text-ink/70">{profile.advisory}</p>
                    <div className="mt-4 space-y-3">
                      {profile.subscriptions.map((subscription) => {
                        const selected = (draftSelections[profile.source] ?? []).includes(subscription.key);
                        return (
                          <label
                            key={subscription.key}
                            className={`block rounded-[18px] border px-4 py-3 ${
                              subscription.available
                                ? "border-black/5 bg-canvas"
                                : "border-black/5 bg-black/5"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              <input
                                type="checkbox"
                                checked={selected}
                                disabled={!subscription.available}
                                onChange={() => toggleSubscription(profile.source, subscription.key)}
                                className="mt-1 h-4 w-4 accent-signal"
                              />
                              <div className="flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <p className="text-sm font-semibold text-ink">{subscription.label}</p>
                                  {subscription.recommended ? <span className="pill">{t("settings.recommended")}</span> : null}
                                  {!subscription.available ? <span className="pill">{t("settings.blocked")}</span> : null}
                                </div>
                                <p className="mt-2 text-sm text-ink/65">{subscription.description}</p>
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <p className="eyebrow">{t("settings.scheduler")}</p>
          <h2 className="panel-title">{t("settings.registeredJobs")}</h2>
          <div className="mt-5 space-y-3">
            {jobs.length === 0 ? (
              <div className="rounded-[22px] bg-canvas px-4 py-3 text-sm text-ink/65">
                {t("settings.noJobs")}
              </div>
            ) : null}
            {jobs.map((job) => (
              <div key={job.id} className="rounded-[22px] bg-canvas px-4 py-3">
                <p className="font-display text-lg">{job.id}</p>
                <p className="mt-2 text-sm text-ink/65">{job.trigger}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.18em] text-ink/45">{job.next_run_time}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
