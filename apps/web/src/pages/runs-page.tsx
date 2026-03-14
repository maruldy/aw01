import { useEffect, useMemo, useState } from "react";

import { getRun, listWorkItems } from "../lib/api";
import type { ExecutionRun, WorkItem } from "../lib/types";
import { useRunStream } from "../hooks/use-run-stream";

export function RunsPage() {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const streamEvents = useRunStream(selectedThreadId);

  useEffect(() => {
    async function load() {
      const workItems = await listWorkItems();
      setItems(workItems);
      if (workItems[0]) {
        setSelectedThreadId(workItems[0].thread_id);
      }
    }
    void load();
  }, []);

  useEffect(() => {
    if (!selectedThreadId) {
      return;
    }
    void getRun(selectedThreadId).then(setRun);
  }, [selectedThreadId]);

  const mergedEvents = useMemo(() => {
    return [...(run?.events ?? []), ...streamEvents];
  }, [run?.events, streamEvents]);

  return (
    <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
      <div className="panel">
        <p className="eyebrow">Execution runs</p>
        <h1 className="panel-title">Track supervisor state</h1>
        <div className="mt-5 space-y-3">
          {items.map((item) => (
            <button
              key={item.thread_id}
              type="button"
              onClick={() => setSelectedThreadId(item.thread_id)}
              className={`w-full rounded-[22px] border px-4 py-4 text-left transition ${
                selectedThreadId === item.thread_id ? "border-ocean bg-ocean/10" : "border-black/5 bg-white/70"
              }`}
            >
              <p className="text-xs uppercase tracking-[0.18em] text-ink/45">{item.source}</p>
              <p className="mt-2 font-display text-lg">{item.title}</p>
              <p className="mt-2 text-sm text-ink/60">{item.thread_id}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Run detail</p>
            <h2 className="panel-title">{run?.current_step ?? "No run selected"}</h2>
          </div>
          <span className="pill">{run?.status ?? "idle"}</span>
        </div>

        <div className="mt-6 space-y-3">
          {mergedEvents.map((event, index) => (
            <div key={`${index}-${JSON.stringify(event)}`} className="rounded-[20px] border border-black/5 bg-white/80 p-4">
              <pre className="whitespace-pre-wrap text-sm text-ink/75">{JSON.stringify(event, null, 2)}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
