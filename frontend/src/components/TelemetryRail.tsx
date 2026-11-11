import { useState } from "react";
import { Plus, Play, Trash2 } from "lucide-react";
import type {
  FactItem,
  RecallItem,
  RoutineItem,
  RouterModelRow,
  RouterShiftItem,
  ToolItem
} from "../types";
import { RouterPanel } from "./RouterPanel";

export type RailTab = "router" | "tools" | "memory" | "routines";

interface TelemetryRailProps {
  activeTab: RailTab;
  onTabChange: (tab: RailTab) => void;
  models: RouterModelRow[];
  shifts: RouterShiftItem[];
  pinnedModelId: string | null;
  onPinModel: (id: string | null) => void;
  onToggleModel: (id: string, disabled: boolean) => void;
  onRefreshModels: () => void;
  tools: ToolItem[];
  facts: FactItem[];
  recallEvents: RecallItem[];
  recallEnabled: boolean;
  onToggleRecall: (enabled: boolean) => void;
  onAddFact: (key: string, value: string) => void;
  onDeleteFact: (id: number) => void;
  routines: RoutineItem[];
  onRunBriefing: () => void;
  onScheduleTimer: (label: string, delaySec: number) => void;
}

export function TelemetryRail(props: TelemetryRailProps) {
  const [factKey, setFactKey] = useState("");
  const [factVal, setFactVal] = useState("");
  const [timerLabel, setTimerLabel] = useState("");
  const [timerMinutes, setTimerMinutes] = useState("5");

  const tabs: Array<{ id: RailTab; label: string }> = [
    { id: "router", label: "Router" },
    { id: "tools", label: "Tools & MCP" },
    { id: "memory", label: "Memory" },
    { id: "routines", label: "Proactive" }
  ];

  return (
    <aside className="koda-panel" aria-label="Telemetry & Control Rail">
      <div className="koda-tabs" role="tablist" aria-label="Inspector views">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={props.activeTab === t.id}
            className={`koda-tab ${props.activeTab === t.id ? "koda-tab--active" : ""}`}
            onClick={() => props.onTabChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="koda-rail-body">
        {props.activeTab === "router" ? (
          <RouterPanel
            models={props.models}
            shifts={props.shifts}
            pinnedModelId={props.pinnedModelId}
            onPinModel={props.onPinModel}
            onToggleModel={props.onToggleModel}
            onRefresh={props.onRefreshModels}
          />
        ) : null}

        {props.activeTab === "tools" ? (
          <>
            <div className="koda-mono koda-muted">{props.tools.length} SAFETY-GATED CAPABILITIES</div>
            {props.tools.map((tool) => (
              <div key={tool.name} className="koda-card">
                <div className="koda-row-between">
                  <strong className="koda-mono">{tool.name}</strong>
                  <span
                    className={`koda-pill ${
                      tool.tier === "AUTO"
                        ? "koda-pill--emerald"
                        : tool.tier === "NOTIFY"
                        ? "koda-pill--cyan"
                        : "koda-pill--gold"
                    }`}
                  >
                    {tool.tier}
                  </span>
                </div>
                <div className="koda-muted" style={{ fontSize: 12 }}>
                  {tool.description}
                </div>
              </div>
            ))}
          </>
        ) : null}

        {props.activeTab === "memory" ? (
          <>
            <form
              className="koda-card"
              onSubmit={(e) => {
                e.preventDefault();
                if (!factKey.trim() || !factVal.trim()) return;
                props.onAddFact(factKey.trim(), factVal.trim());
                setFactKey("");
                setFactVal("");
              }}
            >
              <div className="koda-mono koda-muted">PIN USER FACT</div>
              <div className="koda-omnibar-row">
                <input
                  className="koda-input"
                  aria-label="Memory fact key"
                  placeholder="Key (e.g. editor)"
                  value={factKey}
                  onChange={(e) => setFactKey(e.target.value)}
                />
                <input
                  className="koda-input"
                  aria-label="Memory fact value"
                  placeholder="Value (e.g. VS Code)"
                  value={factVal}
                  onChange={(e) => setFactVal(e.target.value)}
                />
                <button type="submit" className="koda-btn koda-btn--primary" aria-label="Save memory fact">
                  <Plus size={14} aria-hidden="true" />
                </button>
              </div>
            </form>

            {props.facts.map((f) => (
              <div key={f.id} className="koda-card">
                <div className="koda-row-between">
                  <span className="koda-mono">{f.key}</span>
                  <button
                    type="button"
                    className="koda-btn"
                    aria-label={`Delete fact ${f.key}`}
                    onClick={() => props.onDeleteFact(f.id)}
                  >
                    <Trash2 size={12} aria-hidden="true" />
                  </button>
                </div>
                <div>{f.value}</div>
              </div>
            ))}

            <div className="koda-card">
              <div className="koda-row-between">
                <span className="koda-mono">SCREENPIPE-LITE RECALL</span>
                <button
                  type="button"
                  aria-label={props.recallEnabled ? "Disable Screenpipe-lite recall" : "Enable Screenpipe-lite recall"}
                  className={props.recallEnabled ? "koda-btn koda-btn--primary" : "koda-btn"}
                  onClick={() => props.onToggleRecall(!props.recallEnabled)}
                >
                  {props.recallEnabled ? "Enabled (Filtered)" : "Opt-In Off"}
                </button>
              </div>
              {props.recallEvents.length === 0 ? (
                <div className="koda-muted" style={{ fontSize: 12 }}>
                  Privacy-filtered local window timeline has no entries yet.
                </div>
              ) : (
                props.recallEvents.map((ev) => (
                  <div key={ev.id} className="koda-mono koda-muted">
                    [{ev.app_name}] {ev.window_title}
                  </div>
                ))
              )}
            </div>
          </>
        ) : null}

        {props.activeTab === "routines" ? (
          <>
            <div className="koda-card">
              <div className="koda-row-between">
                <strong>Daily Morning Briefing</strong>
                <button
                  type="button"
                  className="koda-btn koda-btn--primary"
                  aria-label="Run daily morning briefing"
                  onClick={props.onRunBriefing}
                >
                  <Play size={13} aria-hidden="true" />
                  Run Briefing
                </button>
              </div>
              <div className="koda-muted" style={{ fontSize: 12 }}>
                Synthesizes live CPU/RAM stats, facts, routines, and recall using Lane 1M Deep ($0).
              </div>
            </div>

            <form
              className="koda-card"
              onSubmit={(e) => {
                e.preventDefault();
                const mins = Math.max(0.1, Number.parseFloat(timerMinutes) || 1);
                if (!timerLabel.trim()) return;
                props.onScheduleTimer(timerLabel.trim(), Math.round(mins * 60));
                setTimerLabel("");
              }}
            >
              <div className="koda-mono koda-muted">PROACTIVE TIMER</div>
              <div className="koda-omnibar-row">
                <input
                  className="koda-input"
                  aria-label="Timer reminder label"
                  placeholder="Label (e.g. Standup)"
                  value={timerLabel}
                  onChange={(e) => setTimerLabel(e.target.value)}
                />
                <input
                  className="koda-input"
                  style={{ maxWidth: 74 }}
                  aria-label="Timer duration in minutes"
                  type="number"
                  min="0.1"
                  step="0.5"
                  value={timerMinutes}
                  onChange={(e) => setTimerMinutes(e.target.value)}
                />
                <button type="submit" className="koda-btn" aria-label="Schedule reminder timer">
                  <Plus size={14} aria-hidden="true" />
                </button>
              </div>
            </form>

            {props.routines.length === 0 ? (
              <div className="koda-card koda-muted">No custom routines saved yet.</div>
            ) : (
              props.routines.map((rt) => (
                <div key={rt.id} className="koda-card">
                  <div className="koda-row-between">
                    <strong>{rt.name}</strong>
                    <span className="koda-pill">{rt.cron_expr || "Manual"}</span>
                  </div>
                  <div className="koda-mono koda-muted">Trigger: {rt.trigger_phrase || "—"}</div>
                </div>
              ))
            )}
          </>
        ) : null}
      </div>
    </aside>
  );
}
