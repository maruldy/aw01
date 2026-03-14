import { useEffect, useState } from "react";

import {
  getAllowedActions,
  getGitHubRecommendedRepos,
  getProfiles,
  getSchedulerJobs,
  updateAllowedActions,
  updateConnectorConfig,
  updateSubscriptions,
  validateProfile
} from "../lib/api";
import { useTranslation } from "../lib/i18n";
import type { ConnectorProfile, GitHubRecommendedRepo } from "../lib/types";

const TAB_ORDER = ["slack", "jira", "confluence", "github"] as const;

export function SettingsPage() {
  const { t } = useTranslation();
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [activeTab, setActiveTab] = useState<string>(TAB_ORDER[0]);
  const [validation, setValidation] = useState<Record<string, string>>({});
  const [draftConfigValues, setDraftConfigValues] = useState<Record<string, Record<string, string>>>({});
  const [editingSensitive, setEditingSensitive] = useState<Record<string, boolean>>({});
  const [draftSelections, setDraftSelections] = useState<Record<string, string[]>>({});
  const [jobs, setJobs] = useState<Array<Record<string, string>>>([]);
  const [recommendedRepos, setRecommendedRepos] = useState<GitHubRecommendedRepo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [manualRepoInput, setManualRepoInput] = useState("");
  const [availableActions, setAvailableActions] = useState<Array<{ key: string; label: string; description: string }>>([]);
  const [allowedActions, setAllowedActions] = useState<string[]>([]);

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

  }

  useEffect(() => {
    async function load() {
      const [profilePayload, jobsPayload] = await Promise.all([getProfiles(), getSchedulerJobs()]);
      await applyProfiles(profilePayload.profiles);
      setJobs(jobsPayload.jobs);
    }
    void load();
  }, []);

  useEffect(() => {
    if (activeTab !== "github") return;
    const githubProfile = profiles.find((p) => p.source === "github");
    if (!githubProfile?.identity) return;
    setLoadingRepos(true);
    getGitHubRecommendedRepos()
      .then((payload) => setRecommendedRepos(payload.repositories))
      .catch(() => setRecommendedRepos([]))
      .finally(() => setLoadingRepos(false));
  }, [activeTab, profiles]);

  useEffect(() => {
    getAllowedActions(activeTab)
      .then((data) => {
        setAvailableActions(data.available);
        setAllowedActions(data.allowed);
      })
      .catch(() => {
        setAvailableActions([]);
        setAllowedActions([]);
      });
  }, [activeTab]);

  function toggleAction(key: string) {
    const next = allowedActions.includes(key)
      ? allowedActions.filter((a) => a !== key)
      : [...allowedActions, key];
    setAllowedActions(next);
    void updateAllowedActions(activeTab, next);
  }

  function getSelectedRepos(): string[] {
    const raw = draftConfigValues["github"]?.github_repository ?? "";
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }

  function setSelectedRepos(repos: string[]) {
    updateConfigValue("github", "github_repository", repos.join(","));
  }

  function toggleRepo(repoName: string) {
    const current = getSelectedRepos();
    const next = current.includes(repoName)
      ? current.filter((r) => r !== repoName)
      : [...current, repoName];
    setSelectedRepos(next);
    void updateConnectorConfig("github", { github_repository: next.join(",") });
  }

  function addManualRepo() {
    const repo = manualRepoInput.trim();
    if (!repo) return;
    const current = getSelectedRepos();
    if (!current.includes(repo)) {
      const next = [...current, repo];
      setSelectedRepos(next);
      void updateConnectorConfig("github", { github_repository: next.join(",") });
    }
    setManualRepoInput("");
  }

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
      const next = [...current];
      void updateSubscriptions(source, next);
      return {
        ...previous,
        [source]: next
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

  const activeProfile = profiles.find((p) => p.source === activeTab);

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

          {/* Tab bar */}
          <div className="mt-4 flex gap-2">
            {TAB_ORDER.map((source) => {
              const profile = profiles.find((p) => p.source === source);
              const isActive = activeTab === source;
              return (
                <button
                  key={source}
                  type="button"
                  onClick={() => setActiveTab(source)}
                  className={`flex items-center gap-2 rounded-[18px] px-4 py-2.5 text-sm font-semibold transition ${
                    isActive
                      ? "bg-ink text-canvas"
                      : "bg-sand/40 text-ink/70 hover:bg-sand/70 hover:text-ink"
                  }`}
                >
                  <span className="capitalize">{source}</span>
                  {profile ? (
                    <span className={`h-2 w-2 rounded-full ${profile.configured ? "bg-pine" : "bg-signal"}`} />
                  ) : null}
                </button>
              );
            })}
          </div>

          {/* Active profile content */}
          {activeProfile ? (
            <div className="mt-5">
              <div className="rounded-[22px] border border-black/5 bg-white/80 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-display text-xl">{activeProfile.name}</p>
                    <p className="mt-1 text-sm text-ink/60">{activeProfile.source} · {activeProfile.mode}</p>
                    {activeProfile.identity ? (
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-pine">
                        {t("settings.identity")}: {activeProfile.identity}
                      </p>
                    ) : null}
                  </div>
                </div>
                {!activeProfile.configured ? (
                  <div className="mt-3 rounded-[18px] bg-signal/10 px-4 py-3">
                    <p className="text-sm text-ink/75">
                      {validation[activeProfile.source] ?? activeProfile.message}
                    </p>
                    {activeProfile.missing_fields.length > 0 ? (
                      <p className="mt-2 text-xs uppercase tracking-[0.18em] text-signal">
                        {t("settings.missing")}: {activeProfile.missing_fields.join(", ")}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-4 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                  {activeProfile.source === "github" ? (
                    <div className="rounded-[18px] border border-black/5 bg-white/90 p-4 lg:col-span-2">
                      <p className="eyebrow">{t("settings.recommendedRepos")}</p>

                      {loadingRepos ? (
                        <p className="mt-4 text-sm text-ink/50">{t("settings.loadingRepos")}</p>
                      ) : recommendedRepos.length > 0 ? (
                        <div className="mt-4 grid gap-2 md:grid-cols-2">
                          {recommendedRepos.map((repo) => {
                            const checked = getSelectedRepos().includes(repo.full_name);
                            return (
                              <label
                                key={repo.full_name}
                                className={`flex items-center gap-3 rounded-[14px] border px-3 py-2.5 transition ${
                                  checked ? "border-ocean/30 bg-ocean/5" : "border-black/5 bg-canvas"
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => toggleRepo(repo.full_name)}
                                  className="h-4 w-4 accent-signal"
                                />
                                <div className="flex-1 min-w-0">
                                  <p className="truncate text-sm font-medium text-ink">{repo.full_name}</p>
                                </div>
                                <span className="shrink-0 text-xs text-ink/50">
                                  {repo.activity_count} {t("settings.activityCount")}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      ) : null}

                      <div className="mt-4">
                        <p className="text-sm font-semibold text-ink">{t("settings.addRepoManually")}</p>
                        <div className="mt-2 flex gap-2">
                          <input
                            type="text"
                            value={manualRepoInput}
                            onChange={(e) => setManualRepoInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addManualRepo(); } }}
                            placeholder={t("settings.addRepoPlaceholder")}
                            className="flex-1 rounded-[14px] border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-signal"
                          />
                          <button
                            type="button"
                            onClick={addManualRepo}
                            className="rounded-[14px] bg-ocean px-4 py-2 text-sm font-semibold text-white"
                          >
                            {t("settings.addRepo")}
                          </button>
                        </div>
                      </div>

                      {getSelectedRepos().length > 0 ? (
                        <div className="mt-4">
                          <p className="text-sm font-semibold text-ink">{t("settings.selectedRepos")}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {getSelectedRepos().map((repo) => (
                              <span
                                key={repo}
                                className="inline-flex items-center gap-1.5 rounded-full bg-ink/10 px-3 py-1 text-sm text-ink"
                              >
                                {repo}
                                <button
                                  type="button"
                                  onClick={() => toggleRepo(repo)}
                                  className="text-ink/40 hover:text-ink"
                                >
                                  ×
                                </button>
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <p className="mt-4 text-sm text-ink/50">{t("settings.noReposSelected")}</p>
                      )}
                    </div>
                  ) : null}

                  {activeProfile.webhook ? (
                    <div className="rounded-[18px] border border-black/5 bg-white/90 p-4 lg:col-span-2">
                      <p className="eyebrow">{t("settings.webhookIntake")}</p>
                      <div className="mt-3 rounded-[16px] bg-canvas px-4 py-3">
                        <p className="text-sm font-semibold text-ink">{t("settings.callbackUrl")}</p>
                        <p className="mt-2 break-all text-sm text-ink/70">
                          {activeProfile.webhook.callback_url}
                        </p>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div className="rounded-[16px] bg-canvas px-4 py-3">
                          <p className="text-sm font-semibold text-ink">{t("settings.verification")}</p>
                          <p className="mt-2 text-sm text-ink/70">
                            {activeProfile.webhook.verification_mode}
                          </p>
                          {activeProfile.webhook.secret_env_key ? (
                            <p className="mt-2 text-xs uppercase tracking-[0.18em] text-pine">
                              {t("settings.secretEnv")}: {activeProfile.webhook.secret_env_key}
                            </p>
                          ) : null}
                        </div>
                        <div className="rounded-[16px] bg-canvas px-4 py-3">
                          <p className="text-sm font-semibold text-ink">{t("settings.recommendedEvents")}</p>
                          <p className="mt-2 text-sm text-ink/70">
                            {activeProfile.webhook.recommended_events.join(", ")}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 space-y-2">
                        {activeProfile.webhook.setup_notes.map((note) => (
                          <div key={note} className="rounded-[16px] bg-canvas px-4 py-3 text-sm text-ink/70">
                            {note}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="rounded-[18px] border border-black/5 bg-white/90 p-4">
                    <p className="eyebrow">{t("settings.allowedActions")}</p>
                    {availableActions.length > 0 ? (
                      <div className="mt-3 space-y-2">
                        {availableActions.map((action) => {
                          const checked = allowedActions.includes(action.key);
                          return (
                            <label
                              key={action.key}
                              className={`flex items-center gap-3 rounded-[14px] border px-4 py-3 transition ${
                                checked ? "border-ocean/30 bg-ocean/5" : "border-black/5 bg-canvas"
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleAction(action.key)}
                                className="h-4 w-4 accent-signal"
                              />
                              <div>
                                <p className="text-sm font-semibold text-ink">{action.label}</p>
                                <p className="mt-0.5 text-xs text-ink/55">{action.description}</p>
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="mt-3 text-sm text-ink/50">{t("settings.noActionsAvailable")}</p>
                    )}
                  </div>

                  <div className="rounded-[18px] border border-black/5 bg-white/90 p-4">
                    <p className="eyebrow">{t("settings.capabilityProbe")}</p>
                    <div className="mt-3 space-y-3">
                      {activeProfile.capabilities.map((capability) => (
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
                    <p className="mt-3 text-sm leading-7 text-ink/70">{activeProfile.advisory}</p>
                    <div className="mt-4 space-y-3">
                      {activeProfile.subscriptions.map((subscription) => {
                        const selected = (draftSelections[activeProfile.source] ?? []).includes(subscription.key);
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
                                onChange={() => toggleSubscription(activeProfile.source, subscription.key)}
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
            </div>
          ) : null}
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
