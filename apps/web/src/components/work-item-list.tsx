import { useTranslation } from "../lib/i18n";
import type { WorkItem } from "../lib/types";

interface WorkItemListProps {
  items: WorkItem[];
  selectedId?: string;
  onSelect: (item: WorkItem) => void;
  onToggle: (item: WorkItem) => void;
}

export function WorkItemList({ items, selectedId, onSelect, onToggle }: WorkItemListProps) {
  const { t } = useTranslation();

  return (
    <div className="panel">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow">{t("workList.eyebrow")}</p>
          <h2 className="panel-title">{t("workList.title")}</h2>
        </div>
        <span className="pill">{items.length} {t("workList.items")}</span>
      </div>

      <div className="mt-5 space-y-2">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => (item.id === selectedId ? onToggle(item) : onSelect(item))}
            className={`w-full rounded-[18px] border px-4 py-3 text-left transition ${
              item.id === selectedId
                ? "border-ocean/30 bg-ocean/5"
                : "border-black/5 bg-white/70 hover:border-ink/15 hover:bg-white"
            }`}
          >
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase tracking-[0.18em] text-ink/45">{item.source}</span>
                  <span className="pill text-[10px]">{item.status}</span>
                </div>
                <p className="mt-1 truncate font-display text-base">{item.title}</p>
              </div>
              {item.id === selectedId ? (
                <span className="h-2 w-2 shrink-0 rounded-full bg-ocean" />
              ) : null}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
