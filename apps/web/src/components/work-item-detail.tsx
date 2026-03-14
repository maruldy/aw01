import { useState } from "react";

import type { WorkItem } from "../lib/types";

interface WorkItemDetailProps {
  item: WorkItem | null;
  onDecision: (decision: "accept" | "reject" | "advise" | "defer", comment?: string) => Promise<void>;
}

const decisionButtons = [
  { label: "Accept", value: "accept" as const, style: "bg-pine text-white" },
  { label: "Reject", value: "reject" as const, style: "bg-ink text-white" },
  { label: "Advise", value: "advise" as const, style: "bg-ocean text-white" },
  { label: "Defer", value: "defer" as const, style: "bg-sand text-ink" }
];

export function WorkItemDetail({ item, onDecision }: WorkItemDetailProps) {
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!item) {
    return (
      <div className="panel flex min-h-[540px] items-center justify-center">
        <p className="text-lg text-ink/45">Select a work item to inspect the AI proposal.</p>
      </div>
    );
  }

  async function handleDecision(decision: "accept" | "reject" | "advise" | "defer") {
    setIsSubmitting(true);
    try {
      await onDecision(decision, comment);
      setComment("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="panel min-h-[540px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">{item.source} · {item.event_type}</p>
          <h2 className="panel-title mt-2">{item.title}</h2>
        </div>
        <span className="pill">{item.status}</span>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-[24px] bg-sand/45 p-5">
          <p className="eyebrow">AI Proposal</p>
          <p className="mt-3 font-display text-2xl">{item.proposal.summary}</p>
          <p className="mt-4 text-sm leading-7 text-ink/70">{item.body}</p>
          <div className="mt-6 rounded-[20px] bg-white/80 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-ink/45">Suggested action</p>
            <p className="mt-2 text-sm leading-7 text-ink/75">{item.proposal.suggested_action}</p>
          </div>
        </section>

        <section className="rounded-[24px] bg-white/80 p-5">
          <p className="eyebrow">Human control</p>
          <p className="mt-3 text-sm leading-7 text-ink/70">
            Keep execution safe. Accept to allow managed action. Use advise when you want the AI to revise direction without fully rejecting the task.
          </p>
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="Add guidance, constraints, or rationale."
            className="mt-5 h-32 w-full rounded-[20px] border border-black/10 bg-canvas px-4 py-3 text-sm outline-none transition focus:border-signal"
          />
          <div className="mt-5 grid grid-cols-2 gap-3">
            {decisionButtons.map((button) => (
              <button
                key={button.value}
                type="button"
                disabled={isSubmitting}
                onClick={() => handleDecision(button.value)}
                className={`rounded-[18px] px-4 py-3 text-sm font-semibold transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:opacity-60 ${button.style}`}
              >
                {button.label}
              </button>
            ))}
          </div>
          {item.decision_comment ? (
            <div className="mt-5 rounded-[18px] border border-black/5 bg-canvas px-4 py-3">
              <p className="text-xs uppercase tracking-[0.18em] text-ink/45">Latest operator note</p>
              <p className="mt-2 text-sm text-ink/75">{item.decision_comment}</p>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
