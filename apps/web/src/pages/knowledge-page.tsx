import { useEffect, useState } from "react";

import { getAuditRecent, getHealth, getKnowledgeRecent, getKnowledgeStats } from "../lib/api";
import { StatCard } from "../components/stat-card";

export function KnowledgePage() {
  const [stats, setStats] = useState<{ total: number; avg_iterations: number; by_month: { month: string; count: number }[] } | null>(null);
  const [recent, setRecent] = useState<Array<Record<string, string>>>([]);
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [backfillState, setBackfillState] = useState<string>("idle");

  useEffect(() => {
    async function load() {
      const [nextStats, nextRecent, nextAudit, health] = await Promise.all([
        getKnowledgeStats(),
        getKnowledgeRecent(),
        getAuditRecent(),
        getHealth()
      ]);
      setStats(nextStats);
      setRecent(nextRecent.items);
      setAudit(nextAudit.items);
      setBackfillState(String(health.backfill.state ?? "idle"));
    }
    void load();
  }, []);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard label="Stored analyses" value={stats?.total ?? 0} hint="Accumulated event and decision context." />
        <StatCard label="Average iterations" value={(stats?.avg_iterations ?? 0).toFixed(1)} hint="Mean synthesis iterations per stored analysis." />
        <StatCard label="Backfill state" value={backfillState} hint="Historical backfill pipeline status." />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="panel">
          <p className="eyebrow">Recent knowledge</p>
          <h2 className="panel-title">Stored summaries</h2>
          <div className="mt-5 space-y-3">
            {recent.map((item) => (
              <div key={item.analysis_id} className="rounded-[22px] bg-white/80 p-4">
                <p className="font-display text-lg">{item.ticket_key}</p>
                <p className="mt-2 text-sm text-ink/65">{item.summary}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <p className="eyebrow">Audit stream</p>
          <h2 className="panel-title">Recent operator-visible events</h2>
          <div className="mt-5 space-y-3">
            {audit.map((item, index) => (
              <div key={`${item.created_at ?? index}`} className="rounded-[22px] border border-black/5 bg-canvas px-4 py-3">
                <p className="text-xs uppercase tracking-[0.18em] text-ink/45">{String(item.event_type)}</p>
                <p className="mt-2 text-sm text-ink/70">{JSON.stringify(item.payload)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
