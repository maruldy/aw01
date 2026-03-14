import type { ReactNode } from "react";

export function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint: string }) {
  return (
    <div className="rounded-[24px] border border-black/5 bg-white/75 p-5 shadow-panel">
      <p className="eyebrow">{label}</p>
      <p className="mt-4 font-display text-4xl">{value}</p>
      <p className="mt-3 text-sm text-ink/60">{hint}</p>
    </div>
  );
}
