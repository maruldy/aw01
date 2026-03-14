import { useState } from "react";

import { useTranslation } from "../lib/i18n";
import type { TranslationKey } from "../locales/ko";
import type { WorkItem } from "../lib/types";

interface WorkItemDetailProps {
  item: WorkItem | null;
  onDecision: (decision: "accept" | "reject" | "advise" | "defer", comment?: string) => Promise<void>;
}

const decisionButtons: { labelKey: TranslationKey; value: "accept" | "reject" | "advise" | "defer"; style: string }[] = [
  { labelKey: "detail.accept", value: "accept", style: "bg-pine text-white" },
  { labelKey: "detail.reject", value: "reject", style: "bg-ink text-white" },
  { labelKey: "detail.advise", value: "advise", style: "bg-ocean text-white" },
  { labelKey: "detail.defer", value: "defer", style: "bg-sand text-ink" }
];

export function WorkItemDetail({ item, onDecision }: WorkItemDetailProps) {
  const { t } = useTranslation();
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!item) {
    return (
      <div className="panel flex min-h-[540px] items-center justify-center">
        <p className="text-lg text-ink/45">{t("detail.empty")}</p>
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
          <p className="eyebrow">{t("detail.proposal")}</p>
          <p className="mt-3 font-display text-2xl">{item.proposal.summary}</p>
          <p className="mt-4 text-sm leading-7 text-ink/70">{item.body}</p>
          <div className="mt-6 rounded-[20px] bg-white/80 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-ink/45">{t("detail.suggestedAction")}</p>
            <p className="mt-2 text-sm leading-7 text-ink/75">{item.proposal.suggested_action}</p>
          </div>
        </section>

        <section className="rounded-[24px] bg-white/80 p-5">
          <p className="eyebrow">{t("detail.humanControl")}</p>
          <p className="mt-3 text-sm leading-7 text-ink/70">
            {t("detail.humanControlDesc")}
          </p>
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder={t("detail.placeholder")}
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
                {t(button.labelKey)}
              </button>
            ))}
          </div>
          {item.decision_comment ? (
            <div className="mt-5 rounded-[18px] border border-black/5 bg-canvas px-4 py-3">
              <p className="text-xs uppercase tracking-[0.18em] text-ink/45">{t("detail.operatorNote")}</p>
              <p className="mt-2 text-sm text-ink/75">{item.decision_comment}</p>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
