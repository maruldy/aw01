import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { createIngress, decideWorkItem, getProfiles, listWorkItems } from "../lib/api";
import type { ConnectorProfile, WorkItem } from "../lib/types";
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
    event_type: "github.review_requested",
    title: "Review requested for infra patch",
    body: "Prepare a safe draft PR and summarize potential risk before opening it.",
    external_id: "gh-review-8",
    actor: "octocat"
  }
};

export function InboxPage() {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [source, setSource] = useState<"slack" | "jira" | "github">("slack");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? items[0] ?? null,
    [items, selectedId]
  );

  async function refresh() {
    const [nextItems, nextProfiles] = await Promise.all([listWorkItems(), getProfiles()]);
    setItems(nextItems);
    setProfiles(nextProfiles.profiles);
    if (!selectedId && nextItems[0]) {
      setSelectedId(nextItems[0].id);
    }
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
    if (!selectedItem) {
      return;
    }
    await decideWorkItem(selectedItem.id, decision, comment);
    await refresh();
  }

  const disconnectedProfiles = profiles.filter((profile) => !profile.configured);

  return (
    <div className="space-y-6">
      <section className="panel">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="eyebrow">Supervisor Console</p>
            <h1 className="font-display text-4xl leading-tight lg:text-5xl">
              Push work to the operator.
              <span className="block text-signal">Keep human control at the approval edge.</span>
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={source}
              onChange={(event) => setSource(event.target.value as "slack" | "jira" | "github")}
              className="rounded-[18px] border border-black/10 bg-white px-4 py-3 text-sm"
            >
              <option value="slack">Slack mention</option>
              <option value="jira">Jira update</option>
              <option value="github">GitHub review request</option>
            </select>
            <button
              type="button"
              onClick={simulateEvent}
              disabled={isSubmitting}
              className="rounded-[18px] bg-signal px-5 py-3 text-sm font-semibold text-white transition hover:translate-y-[-1px] disabled:opacity-60"
            >
              {isSubmitting ? "Injecting..." : "Simulate inbound work"}
            </button>
          </div>
        </div>

        {disconnectedProfiles.length > 0 ? (
          <div className="mt-6 rounded-[24px] border border-signal/20 bg-signal/10 p-5">
            <p className="eyebrow text-signal">Connector setup required</p>
            <p className="mt-3 font-display text-2xl">
              실제 사내 이벤트는 아직 들어오지 않습니다.
            </p>
            <p className="mt-3 text-sm leading-7 text-ink/75">
              {disconnectedProfiles.map((profile) => profile.source).join(", ")} 연동이 비어 있습니다.
              Settings에서 자격증명을 연결하면 실제 Jira, Confluence, Slack, GitHub 활동이 inbox로 유입됩니다.
              지금은 데모 이벤트만 주입할 수 있습니다.
            </p>
            <Link
              to="/settings"
              className="mt-4 inline-flex rounded-[18px] bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:translate-y-[-1px]"
            >
              Open setup wizard
            </Link>
          </div>
        ) : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <WorkItemList items={items} selectedId={selectedItem?.id} onSelect={(item) => setSelectedId(item.id)} />
        <WorkItemDetail item={selectedItem} onDecision={handleDecision} />
      </section>
    </div>
  );
}
