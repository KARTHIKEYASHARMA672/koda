import { ArrowRightLeft, CheckCircle2, Clock, RefreshCw, Slash } from "lucide-react";
import type { RouterModelRow, RouterShiftItem } from "../types";

interface RouterPanelProps {
  models: RouterModelRow[];
  shifts: RouterShiftItem[];
  pinnedModelId: string | null;
  onPinModel: (modelId: string | null) => void;
  onToggleModel: (modelId: string, disabled: boolean) => void;
  onRefresh: () => void;
}

function stateBadgeClass(state: RouterModelRow["state"]): string {
  if (state === "HEALTHY") return "koda-pill koda-pill--emerald";
  if (state === "SOFT_SHIFTED" || state === "HALF_OPEN") return "koda-pill koda-pill--gold";
  if (state === "COOLDOWN" || state === "DISABLED") return "koda-pill koda-pill--crimson";
  return "koda-pill";
}

function StateIcon({ state }: { state: RouterModelRow["state"] }) {
  if (state === "HEALTHY") return <CheckCircle2 size={12} aria-hidden="true" />;
  if (state === "DISABLED") return <Slash size={12} aria-hidden="true" />;
  return <Clock size={12} aria-hidden="true" />;
}

export function RouterPanel({
  models,
  shifts,
  pinnedModelId,
  onPinModel,
  onToggleModel,
  onRefresh
}: RouterPanelProps) {
  return (
    <>
      <div className="koda-row-between">
        <span className="koda-mono koda-muted">{models.length} FREE OPENCODE MODELS</span>
        <button type="button" className="koda-btn" onClick={onRefresh} aria-label="Refresh free OpenCode model pool">
          <RefreshCw size={13} aria-hidden="true" />
          Refresh Pool
        </button>
      </div>

      {models.map((m) => {
        const isPinned = pinnedModelId === m.id;
        return (
          <div key={m.id} className="koda-card">
            <div className="koda-row-between">
              <strong style={{ fontSize: 13 }}>{m.id}</strong>
              <span className={stateBadgeClass(m.state)}>
                <StateIcon state={m.state} />
                {m.state}
              </span>
            </div>
            <div className="koda-row-between koda-mono koda-muted">
              <span>{m.input_capabilities.join(" · ")}</span>
              <span>
                {m.ewma_latency_ms > 0 ? `${Math.round(m.ewma_latency_ms)}ms` : "—"} · {m.total_tokens} tok
              </span>
            </div>
            {m.last_error ? (
              <div className="koda-mono" style={{ color: "var(--accent-crimson-ink)" }}>
                Last error: {m.last_error}
              </div>
            ) : null}
            <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
              <button
                type="button"
                className={isPinned ? "koda-btn koda-btn--primary" : "koda-btn"}
                aria-label={isPinned ? `Unpin ${m.id}` : `Pin ${m.id}`}
                onClick={() => onPinModel(isPinned ? null : m.id)}
              >
                {isPinned ? "Pinned" : "Pin"}
              </button>
              <button
                type="button"
                className="koda-btn"
                aria-label={m.state === "DISABLED" ? `Enable ${m.id}` : `Disable ${m.id}`}
                onClick={() => onToggleModel(m.id, m.state !== "DISABLED")}
              >
                {m.state === "DISABLED" ? "Enable" : "Disable"}
              </button>
            </div>
          </div>
        );
      })}

      <div style={{ marginTop: 6 }}>
        <div className="koda-mono koda-muted" style={{ marginBottom: 6 }}>
          RECENT AUTOMATIC FAILOVERS
        </div>
        {shifts.length === 0 ? (
          <div className="koda-card koda-muted">No failovers triggered yet. All routes nominal.</div>
        ) : (
          shifts.map((s) => (
            <div key={s.id} className="koda-card">
              <div className="koda-row-between">
                <span className="koda-pill koda-pill--gold">
                  <ArrowRightLeft size={12} aria-hidden="true" />
                  {s.from_model} → {s.to_model}
                </span>
                <span className="koda-mono koda-muted">{s.lane}</span>
              </div>
              <div className="koda-mono koda-muted">{s.reason}</div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
