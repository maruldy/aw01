import type { WorkItem } from "../lib/types";

interface WorkItemListProps {
  items: WorkItem[];
  selectedId?: string;
  onSelect: (item: WorkItem) => void;
}

export function WorkItemList({ items, selectedId, onSelect }: WorkItemListProps) {
  return (
    <div className="panel">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow">AI Inbox</p>
          <h2 className="panel-title">Incoming work</h2>
        </div>
        <span className="pill">{items.length} items</span>
      </div>

      <div className="mt-5 space-y-3">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item)}
            className={`w-full rounded-[22px] border p-4 text-left transition ${
              item.id === selectedId
                ? "border-signal bg-signal/10"
                : "border-black/5 bg-white/70 hover:border-ink/20 hover:bg-white"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-ink/45">{item.source}</p>
                <p className="mt-2 font-display text-lg">{item.title}</p>
                <p className="mt-2 line-clamp-2 text-sm text-ink/65">{item.proposal.summary}</p>
              </div>
              <span className="pill">{item.status}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
