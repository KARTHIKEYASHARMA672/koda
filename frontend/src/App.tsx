import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRightLeft, Camera, Mic, MicOff, Send, ShieldCheck, Square } from "lucide-react";
import { AcousticOrb } from "./components/AcousticOrb";
import { ApprovalBanner } from "./components/ApprovalBanner";
import { TelemetryRail, type RailTab } from "./components/TelemetryRail";
import type {
  ChatTimelineMessage,
  FactItem,
  HealthStatus,
  KodaStateName,
  LaneName,
  PendingApproval,
  RecallItem,
  RoutineItem,
  RouterModelRow,
  RouterShiftItem,
  ToolItem
} from "./types";

const QUICK_PROMPTS = [
  "Check live CPU, RAM, and RTX GPU telemetry",
  "Summarize my workspace git status",
  "Open a headless browser check on example.com",
  "Run morning briefing"
];

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [kodaState, setKodaState] = useState<KodaStateName>("idle");
  const [models, setModels] = useState<RouterModelRow[]>([]);
  const [shifts, setShifts] = useState<RouterShiftItem[]>([]);
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [facts, setFacts] = useState<FactItem[]>([]);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [routines, setRoutines] = useState<RoutineItem[]>([]);
  const [recallEvents, setRecallEvents] = useState<RecallItem[]>([]);
  const [recallEnabled, setRecallEnabled] = useState(false);
  const [listening, setListening] = useState(false);

  const [messages, setMessages] = useState<ChatTimelineMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [lane, setLane] = useState<LaneName>("auto");
  const [pinnedModelId, setPinnedModelId] = useState<string | null>(null);
  const [attachedFiles, setAttachedFiles] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [errorBanner, setErrorBanner] = useState("");
  const [activeTab, setActiveTab] = useState<RailTab>("router");
  const [mobilePane, setMobilePane] = useState<"chat" | "telemetry">("chat");

  const inputRef = useRef<HTMLInputElement | null>(null);

  const loadSnapshot = useCallback(async () => {
    try {
      const [hRes, rRes, aRes, fRes, tRes, rtRes, rcRes, rcStRes, vRes] = await Promise.all([
        fetch("/health"),
        fetch("/api/router/status"),
        fetch("/api/approvals?status=pending"),
        fetch("/api/memory/facts"),
        fetch("/api/tools"),
        fetch("/api/routines"),
        fetch("/api/recall"),
        fetch("/api/recall/status"),
        fetch("/api/voice/status")
      ]);

      if (hRes.ok) {
        const hData = (await hRes.json()) as HealthStatus;
        setHealth(hData);
        setKodaState(hData.state || "idle");
      }
      if (rRes.ok) {
        const rData = await rRes.json();
        setModels(rData.models ?? []);
        setShifts(rData.recent_shifts ?? []);
      }
      if (aRes.ok) {
        const aData = await aRes.json();
        setApprovals(aData.approvals ?? []);
      }
      if (fRes.ok) {
        const fData = await fRes.json();
        setFacts(fData.facts ?? []);
      }
      if (tRes.ok) {
        const tData = await tRes.json();
        setTools(tData.tools ?? []);
      }
      if (rtRes.ok) {
        const rtData = await rtRes.json();
        setRoutines(rtData.routines ?? []);
      }
      if (rcRes.ok) {
        const rcData = await rcRes.json();
        setRecallEvents(rcData.events ?? []);
      }
      if (rcStRes.ok) {
        const rcStData = await rcStRes.json();
        setRecallEnabled(Boolean(rcStData.recall_enabled));
      }
      if (vRes.ok) {
        const vData = await vRes.json();
        setListening(Boolean(vData.listening));
      }
    } catch {
      // Gateway might still be warming up
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof WebSocket === "undefined") return;
    let closed = false;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/events`);

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "koda_state" && msg.payload?.state) {
          setKodaState(msg.payload.state);
        } else if (msg.type === "router_shift" && msg.payload) {
          setShifts((prev) => [{ id: Date.now(), ...msg.payload }, ...prev].slice(0, 25));
        } else if (msg.type === "approval_required" && msg.payload) {
          setApprovals((prev) => [msg.payload, ...prev.filter((a) => a.id !== msg.payload.id)]);
        } else if (msg.type === "approval_resolved" && msg.payload?.id) {
          setApprovals((prev) => prev.filter((a) => a.id !== msg.payload.id));
        }
      } catch {
        // Ignore malformed WS frames
      }
    };

    ws.onerror = () => {
      if (!closed) {
        ws.close();
      }
    };

    return () => {
      closed = true;
      ws.close();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === "Space") {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === "Escape") {
        setErrorBanner("");
        setAttachedFiles([]);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText ?? prompt).trim();
    if (!text || sending) return;
    setErrorBanner("");
    if (!overrideText) setPrompt("");

    const userMsg: ChatTimelineMessage = {
      id: `u_${Date.now()}`,
      role: "user",
      text
    };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    setKodaState("thinking");

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: text,
          conversation_id: "default",
          lane: lane === "auto" ? null : lane,
          preferred_model_id: pinnedModelId,
          files: attachedFiles.length > 0 ? attachedFiles : null,
          has_image: attachedFiles.length > 0
        })
      });
      const data = await resp.json();
      if (!resp.ok) {
        setErrorBanner(data?.detail?.error || "All free models temporarily rate-limited.");
      } else {
        const assistantMsg: ChatTimelineMessage = {
          id: `a_${Date.now()}`,
          role: "assistant",
          text: data.reply,
          model_id: data.model_id,
          lane: data.lane,
          cost: data.cost,
          latency_ms: data.latency_ms,
          shifted_from: data.shifted_from,
          shift_reason: data.shift_reason,
          tool_calls: data.tool_calls
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setAttachedFiles([]);
        void loadSnapshot();
      }
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to reach Koda gateway.");
    } finally {
      setSending(false);
      setKodaState("idle");
    }
  };

  const handleResolveApproval = async (approvalId: string, approved: boolean) => {
    await fetch(`/api/approvals/${approvalId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved })
    });
    setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
  };

  const handleCaptureScreen = async () => {
    setErrorBanner("");
    try {
      const resp = await fetch("/api/tools/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "capture_screen", args: {} })
      });
      const data = await resp.json();
      if (resp.ok && data.ok && data.path) {
        setAttachedFiles([data.path]);
        setLane("vision");
      } else {
        setErrorBanner(data?.error || data?.reason || "Screen capture unavailable.");
      }
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : "Screen capture request failed.");
    }
  };

  const handleToggleMic = async () => {
    const next = !listening;
    const resp = await fetch("/api/voice/listen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: next })
    });
    const data = await resp.json();
    setListening(Boolean(data.listening));
    setKodaState(data.listening ? "listening" : "idle");
  };

  const handleBargeIn = async () => {
    await fetch("/api/voice/barge-in", { method: "POST" });
    setKodaState("idle");
  };

  const activeHealthy = models.find((m) => m.id === pinnedModelId || m.state === "HEALTHY")?.id ?? "auto-free";

  return (
    <div className="koda-shell">
      <header className="koda-topbar">
        <div className="koda-brand-group">
          <AcousticOrb state={kodaState} />
          <div>
            <h1 className="koda-title">KODA</h1>
          </div>
          <span className="koda-pill koda-pill--emerald">
            <ShieldCheck size={13} aria-hidden="true" />
            $0.00 HARD CAP
          </span>
          <span className={`koda-pill ${health?.opencode_connected ? "koda-pill--cyan" : "koda-pill--gold"}`}>
            {health?.opencode_connected ? "OPENCODE LIVE" : "OPENCODE STANDBY"} · {activeHealthy}
          </span>
        </div>

        <div className="koda-topbar-actions">
          <button type="button" className="koda-btn" onClick={handleCaptureScreen} aria-label="Capture screen">
            <Camera size={14} aria-hidden="true" />
            Capture Screen
          </button>
          <button
            type="button"
            className={listening ? "koda-btn koda-btn--primary" : "koda-btn"}
            onClick={handleToggleMic}
            aria-label={listening ? "Stop voice capture" : "Start voice capture"}
          >
            {listening ? <MicOff size={14} aria-hidden="true" /> : <Mic size={14} aria-hidden="true" />}
            {listening ? "Listening" : "Voice"}
          </button>
          <button type="button" className="koda-btn" onClick={handleBargeIn} aria-label="Interrupt speech">
            <Square size={13} aria-hidden="true" />
            Barge-In
          </button>
        </div>
      </header>

      <div className="koda-mobile-switch" role="navigation" aria-label="Mobile view switcher">
        <button
          type="button"
          className={mobilePane === "chat" ? "koda-btn koda-btn--primary" : "koda-btn"}
          onClick={() => setMobilePane("chat")}
        >
          Command Stream
        </button>
        <button
          type="button"
          className={mobilePane === "telemetry" ? "koda-btn koda-btn--primary" : "koda-btn"}
          onClick={() => setMobilePane("telemetry")}
        >
          Telemetry Rail ({models.length})
        </button>
      </div>

      <main className="koda-grid">
        <section
          className={`koda-panel ${mobilePane === "telemetry" ? "koda-panel--hidden-mobile" : ""}`}
          aria-label="Conversation Command Stream"
        >
          <div className="koda-stream">
            {messages.length === 0 ? (
              <div className="koda-empty-hero">
                <div className="koda-mono koda-muted">SPATIAL COMMAND DECK · CTRL+SPACE FOCUS</div>
                <h2>Ready at Zero Inference Cost</h2>
                <p>
                  Every turn routes automatically across verified free OpenCode models with stateful context handoff
                  if quota or rate limits trigger.
                </p>
                <div className="koda-chip-row">
                  {QUICK_PROMPTS.map((q) => (
                    <button key={q} type="button" className="koda-btn" onClick={() => handleSend(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <article
                  key={m.id}
                  className={`koda-msg ${m.role === "user" ? "koda-msg--user" : "koda-msg--assistant"}`}
                >
                  <div className="koda-msg-meta">
                    <span>{m.role === "user" ? "YOU" : `KODA · ${m.model_id ?? "free"} (${m.lane ?? "fast"})`}</span>
                    {m.role === "assistant" ? (
                      <span>
                        ${(m.cost ?? 0).toFixed(2)} · {m.latency_ms ?? 0}ms
                      </span>
                    ) : null}
                  </div>
                  {m.shifted_from ? (
                    <div className="koda-pill koda-pill--gold koda-pill--wrap">
                      <ArrowRightLeft size={12} aria-hidden="true" style={{ flexShrink: 0 }} />
                      <span>
                        Failover: {m.shifted_from} → {m.model_id}
                      </span>
                    </div>
                  ) : null}
                  {m.tool_calls && m.tool_calls.length > 0 ? (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {m.tool_calls.map((tc, i) => (
                        <span key={`${m.id}_t_${i}`} className="koda-pill koda-pill--cyan">
                          {tc.tool} [{tc.tier}]
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="koda-msg-body">{m.text}</div>
                </article>
              ))
            )}
          </div>

          <ApprovalBanner approvals={approvals} onResolve={handleResolveApproval} />

          {errorBanner ? (
            <div className="koda-approval-card" style={{ borderColor: "var(--accent-crimson)" }} role="status">
              {errorBanner}
            </div>
          ) : null}

          <form
            className="koda-omnibar"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSend();
            }}
          >
            {attachedFiles.length > 0 ? (
              <div className="koda-pill koda-pill--cyan">
                Attached screen: {attachedFiles[0].split(/[\\/]/).pop()}
              </div>
            ) : null}
            <div className="koda-omnibar-row">
              <select
                className="koda-select"
                aria-label="Routing lane"
                value={lane}
                onChange={(e) => setLane(e.target.value as LaneName)}
              >
                <option value="auto">lane: auto</option>
                <option value="fast">lane: fast</option>
                <option value="vision">lane: vision</option>
                <option value="deep_1m">lane: deep 1M</option>
                <option value="multimodal">lane: audio/video</option>
              </select>
              <input
                ref={inputRef}
                type="text"
                className="koda-input"
                aria-label="Command Koda"
                placeholder="Ask Koda, launch a routine, or inspect screen... (Ctrl+Space)"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
              <button
                type="submit"
                className="koda-btn koda-btn--primary"
                aria-label="Send command"
                disabled={sending || !prompt.trim()}
              >
                <Send size={14} aria-hidden="true" />
                {sending ? "Routing" : "Send"}
              </button>
            </div>
          </form>
        </section>

        <div className={`${mobilePane === "chat" ? "koda-panel--hidden-mobile " : ""}koda-rail-slot`}>
          <TelemetryRail
            activeTab={activeTab}
            onTabChange={setActiveTab}
            models={models}
            shifts={shifts}
            pinnedModelId={pinnedModelId}
            onPinModel={setPinnedModelId}
            onToggleModel={async (id, disabled) => {
              await fetch(`/api/router/models/${id}/state`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ disabled })
              });
              void loadSnapshot();
            }}
            onRefreshModels={async () => {
              await fetch("/api/router/refresh", { method: "POST" });
              void loadSnapshot();
            }}
            tools={tools}
            facts={facts}
            recallEvents={recallEvents}
            recallEnabled={recallEnabled}
            onToggleRecall={async (enabled) => {
              await fetch("/api/recall/toggle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled })
              });
              setRecallEnabled(enabled);
            }}
            onAddFact={async (key, value) => {
              await fetch("/api/memory/facts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ category: "preference", key, value })
              });
              void loadSnapshot();
            }}
            onDeleteFact={async (id) => {
              await fetch(`/api/memory/facts/${id}`, { method: "DELETE" });
              void loadSnapshot();
            }}
            routines={routines}
            onRunBriefing={async () => {
              setMobilePane("chat");
              await handleSend("Generate my daily morning briefing from live system telemetry, facts, and routines.");
            }}
            onScheduleTimer={async (label, delaySec) => {
              await fetch("/api/timers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ label, delay_sec: delaySec })
              });
            }}
          />
        </div>
      </main>
    </div>
  );
}
