import { useEffect, useState } from "react";

import { getProfiles, getSchedulerJobs, triggerBackfill, validateProfile } from "../lib/api";
import type { ConnectorProfile } from "../lib/types";

export function SettingsPage() {
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [validation, setValidation] = useState<Record<string, string>>({});
  const [jobs, setJobs] = useState<Array<Record<string, string>>>([]);

  useEffect(() => {
    async function load() {
      const [profilePayload, jobsPayload] = await Promise.all([getProfiles(), getSchedulerJobs()]);
      setProfiles(profilePayload.profiles);
      setJobs(jobsPayload.jobs);
    }
    void load();
  }, []);

  async function handleValidate(source: string) {
    const result = await validateProfile(source);
    setValidation((previous) => ({
      ...previous,
      [source]: result.ok ? "Connected" : "Missing credentials"
    }));
  }

  async function handleBackfill() {
    await triggerBackfill();
  }

  return (
    <div className="space-y-6">
      <section className="panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="eyebrow">Setup wizard</p>
            <h1 className="panel-title">Validate enterprise connectors</h1>
          </div>
          <button
            type="button"
            onClick={handleBackfill}
            className="rounded-[18px] bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:translate-y-[-1px]"
          >
            Trigger backfill dry run
          </button>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="panel">
          <p className="eyebrow">Connector profiles</p>
          <div className="mt-5 space-y-3">
            {profiles.map((profile) => (
              <div key={profile.source} className="rounded-[22px] border border-black/5 bg-white/80 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-display text-xl">{profile.name}</p>
                    <p className="mt-1 text-sm text-ink/60">{profile.source} · {profile.mode}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleValidate(profile.source)}
                    className="rounded-[16px] bg-ocean px-4 py-2 text-sm font-semibold text-white"
                  >
                    Validate
                  </button>
                </div>
                <div className="mt-3 rounded-[18px] bg-canvas px-4 py-3">
                  <p className="text-sm text-ink/75">
                    {validation[profile.source] ?? profile.message}
                  </p>
                  {!profile.configured ? (
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-signal">
                      Missing: {profile.missing_fields.join(", ")}
                    </p>
                  ) : (
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-pine">Ready for ingestion</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <p className="eyebrow">Scheduler</p>
          <h2 className="panel-title">Registered jobs</h2>
          <div className="mt-5 space-y-3">
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
