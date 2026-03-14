import { useState } from "react";
import { CheckCircle, AlertTriangle, Info, X } from "lucide-react";

import { useTranslation } from "../lib/i18n";
import type { TranslationKey } from "../locales/ko";
import type { WorkItem } from "../lib/types";

function ActionResultBanner({ result }: { result?: Record<string, unknown> | null }) {
  const { t } = useTranslation();
  if (!result) return null;

  const type = String(result.type ?? "");
  const actionResult = (result.result ?? {}) as Record<string, unknown>;
  const ok = Boolean(actionResult.ok);

  if (type === "steering_action" && ok) {
    const url = String(actionResult.html_url ?? "");
    return (
      <div className="mt-4 flex items-start gap-2.5 rounded-[14px] border border-pine/20 bg-pine/5 px-4 py-3">
        <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-pine" />
        <div className="min-w-0 text-sm">
          <p className="font-semibold text-pine">{t("detail.actionSuccess")}</p>
          {url ? (
            <a href={url} target="_blank" rel="noopener noreferrer" className="mt-1 block truncate text-ocean hover:underline">
              {url}
            </a>
          ) : null}
        </div>
      </div>
    );
  }

  if (type === "steering_action" && !ok) {
    const message = String(actionResult.message ?? result.message ?? "");
    return (
      <div className="mt-4 flex items-start gap-2.5 rounded-[14px] border border-signal/20 bg-signal/5 px-4 py-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-signal" />
        <div className="text-sm">
          <p className="font-semibold text-signal">{t("detail.actionFailed")}</p>
          {message ? <p className="mt-1 text-ink/70">{message}</p> : null}
        </div>
      </div>
    );
  }

  if (type === "steering_error") {
    const message = String(result.message ?? "");
    return (
      <div className="mt-4 flex items-start gap-2.5 rounded-[14px] border border-signal/20 bg-signal/5 px-4 py-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-signal" />
        <div className="text-sm">
          <p className="font-semibold text-signal">{t("detail.actionFailed")}</p>
          {message ? <p className="mt-1 text-ink/70">{message}</p> : null}
        </div>
      </div>
    );
  }

  if (type === "steering_skip") {
    const reasoning = String(result.reasoning ?? "");
    return (
      <div className="mt-4 flex items-start gap-2.5 rounded-[14px] border border-black/5 bg-canvas px-4 py-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-ink/45" />
        <div className="text-sm">
          <p className="font-semibold text-ink/60">{t("detail.actionSkipped")}</p>
          {reasoning ? <p className="mt-1 text-ink/60">{reasoning}</p> : null}
        </div>
      </div>
    );
  }

  return null;
}

interface WorkItemDetailProps {
  item: WorkItem | null;
  onDecision: (decision: "accept" | "reject" | "advise" | "defer", comment?: string) => Promise<void>;
  onClose: () => void;
}

type DecisionValue = "accept" | "reject" | "advise" | "defer";

const decisionOptions: { labelKey: TranslationKey; value: DecisionValue }[] = [
  { labelKey: "detail.accept", value: "accept" },
  { labelKey: "detail.reject", value: "reject" },
  { labelKey: "detail.advise", value: "advise" },
  { labelKey: "detail.defer", value: "defer" }
];

export function WorkItemDetail({ item, onDecision, onClose }: WorkItemDetailProps) {
  const { t } = useTranslation();
  const [comment, setComment] = useState("");
  const [decision, setDecision] = useState<DecisionValue>("accept");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!item) return null;

  async function handleExecute() {
    setIsSubmitting(true);
    try {
      await onDecision(decision, comment);
      setComment("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="panel animate-slide-in">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow">{item.source} · {item.event_type}</p>
          <h2 className="panel-title mt-2">{item.title}</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="pill">{item.status}</span>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-xl text-ink/40 transition hover:bg-ink/5 hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-5 space-y-4">
        <section className="rounded-[20px] bg-sand/45 p-5">
          <p className="eyebrow">{t("detail.proposal")}</p>
          <p className="mt-3 font-display text-xl">{item.proposal.summary}</p>
          <p className="mt-3 text-sm leading-7 text-ink/70">{item.body}</p>
          <div className="mt-4 rounded-[16px] bg-white/80 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-ink/45">{t("detail.suggestedAction")}</p>
            <p className="mt-2 text-sm leading-7 text-ink/75">{item.proposal.suggested_action}</p>
          </div>
        </section>

        <section className="rounded-[20px] bg-white/80 p-5">
          <p className="eyebrow">{t("detail.humanControl")}</p>
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder={t("detail.placeholder")}
            className="mt-3 h-20 w-full rounded-[16px] border border-black/10 bg-canvas px-4 py-3 text-sm outline-none transition focus:border-ocean"
          />
          <div className="mt-3 flex items-center gap-2">
            <select
              value={decision}
              onChange={(e) => setDecision(e.target.value as DecisionValue)}
              className="rounded-[14px] border border-black/10 bg-canvas px-4 py-2 text-sm font-semibold outline-none focus:border-ocean"
            >
              {decisionOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{t(opt.labelKey)}</option>
              ))}
            </select>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleExecute}
              className="rounded-[14px] bg-ink px-5 py-2 text-sm font-semibold text-white transition hover:translate-y-[-1px] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {t("detail.execute")}
            </button>
          </div>
          {item.decision_comment ? (
            <div className="mt-4 rounded-[14px] border border-black/5 bg-canvas px-4 py-3">
              <p className="text-xs uppercase tracking-[0.18em] text-ink/45">{t("detail.operatorNote")}</p>
              <p className="mt-2 text-sm text-ink/75">{item.decision_comment}</p>
            </div>
          ) : null}
          <ActionResultBanner result={item.action_result} />
        </section>
      </div>
    </div>
  );
}
