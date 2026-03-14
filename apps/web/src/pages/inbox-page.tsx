import { useCallback, useEffect, useMemo, useState } from "react";

import { createIngress, decideWorkItem, listWorkItems } from "../lib/api";
import { useTranslation } from "../lib/i18n";
import type { WorkItem } from "../lib/types";
import { WorkItemDetail } from "../components/work-item-detail";
import { WorkItemList } from "../components/work-item-list";

const presets = {
  slack: {
    event_type: "slack.mention",
    title: "Mentioned in #platform",
    body: "Can someone explain why the deploy failed?",
    external_id: "demo-slack-1",
    actor: "U123"
  },
  jira: {
    event_type: "jira.updated",
    title: "PROJ-104: rollout follow-up",
    body: "Deployment issue needs impact assessment and mitigation steps.",
    external_id: "PROJ-104",
    actor: "jira-bot"
  },
  github: {
    event_type: "github.pull_request.opened",
    title: "Review requested for infra patch",
    body: "Prepare a safe draft PR and summarize potential risk before opening it.",
    external_id: "gh-review-8",
    actor: "daeyoung-lee",
    metadata: {
      repository: { full_name: "daeyoung-lee/PrivateTasks" },
      sender: { login: "daeyoung-lee" }
    }
  }
};

export function InboxPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [source, setSource] = useState<"slack" | "jira" | "github">("slack");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const selectedItem = useMemo(
    () => (selectedId ? items.find((item) => item.id === selectedId) ?? null : null),
    [items, selectedId]
  );

  const closeDetail = useCallback(() => setSelectedId(null), []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") closeDetail();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeDetail]);

  async function refresh() {
    const nextItems = await listWorkItems();
    setItems(nextItems);
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function simulateEvent() {
    setIsSubmitting(true);
    try {
      const result = await createIngress(source, presets[source]);
      await refresh();
      setSelectedId(result.work_item.id);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDecision(decision: "accept" | "reject" | "advise" | "defer", comment?: string) {
    if (!selectedItem) return;
    await decideWorkItem(selectedItem.id, decision, comment);
    await refresh();
  }

  return (
    <div className="space-y-6">
      <section className="panel">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="eyebrow">{t("inbox.eyebrow")}</p>
            <h1 className="font-display text-2xl">{t("inbox.title")}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={source}
              onChange={(event) => setSource(event.target.value as "slack" | "jira" | "github")}
              className="rounded-[18px] border border-black/10 bg-white px-4 py-2.5 text-sm"
            >
              <option value="slack">{t("inbox.slackMention")}</option>
              <option value="jira">{t("inbox.jiraUpdate")}</option>
              <option value="github">{t("inbox.githubReview")}</option>
            </select>
            <button
              type="button"
              onClick={simulateEvent}
              disabled={isSubmitting}
              className="rounded-[18px] bg-signal px-5 py-2.5 text-sm font-semibold text-white transition hover:translate-y-[-1px] disabled:opacity-60"
            >
              {isSubmitting ? t("inbox.injecting") : t("inbox.simulate")}
            </button>
          </div>
        </div>
      </section>

      <section className={`grid gap-6 ${selectedItem ? "xl:grid-cols-[1fr_1.2fr]" : ""}`}>
        <WorkItemList items={items} selectedId={selectedItem?.id} onSelect={(item) => setSelectedId(item.id)} onToggle={closeDetail} />
        {selectedItem ? (
          <WorkItemDetail
            key={selectedItem.id}
            item={selectedItem}
            onDecision={handleDecision}
            onClose={closeDetail}
          />
        ) : null}
      </section>
    </div>
  );
}
