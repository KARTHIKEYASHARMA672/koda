import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function mockApiFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/health")) {
      return new Response(
        JSON.stringify({
          status: "ok",
          state: "idle",
          allow_paid_models: false,
          free_models_count: 2,
          opencode_connected: true
        })
      );
    }
    if (url.endsWith("/api/router/status")) {
      return new Response(
        JSON.stringify({
          allow_paid_models: false,
          free_models_count: 2,
          models: [
            {
              id: "iceman-free",
              provider_id: "opencode",
              input_capabilities: ["text"],
              tools: true,
              state: "COOLDOWN",
              fail_count: 1,
              ewma_latency_ms: 420,
              total_requests: 3,
              total_tokens: 910,
              cooldown_until: 9999999999,
              last_error: "quota exhausted"
            },
            {
              id: "nemotron-3.5-lightning-free",
              provider_id: "opencode",
              input_capabilities: ["text"],
              tools: true,
              state: "HEALTHY",
              fail_count: 0,
              ewma_latency_ms: 310,
              total_requests: 5,
              total_tokens: 1450,
              cooldown_until: 0,
              last_error: ""
            }
          ],
          recent_shifts: [
            {
              id: 1,
              from_model: "iceman-free",
              to_model: "nemotron-3.5-lightning-free",
              reason: "402 quota exhausted",
              lane: "fast",
              conversation_id: "default",
              created_at: 1700000000
            }
          ]
        })
      );
    }
    if (url.endsWith("/api/approvals?status=pending")) {
      return new Response(
        JSON.stringify({
          approvals: [
            {
              id: "apr_42",
              tool_name: "run_shell",
              args_json: '{"command":"git status"}',
              summary: "Execute shell command: `git status`",
              tier: "CONFIRM",
              status: "pending",
              created_at: 1700000000
            }
          ]
        })
      );
    }
    if (url.endsWith("/api/approvals/apr_42/resolve") && init?.method === "POST") {
      return new Response(JSON.stringify({ id: "apr_42", approved: true }));
    }
    if (url.endsWith("/api/memory/facts")) {
      return new Response(
        JSON.stringify({
          facts: [{ id: 1, category: "identity", key: "preferred_name", value: "Karthikeya" }]
        })
      );
    }
    if (url.endsWith("/api/tools")) {
      return new Response(
        JSON.stringify({
          tools: [{ name: "system_metrics", description: "CPU/RAM/GPU stats", tier: "AUTO" }]
        })
      );
    }
    if (url.endsWith("/api/routines")) {
      return new Response(
        JSON.stringify({
          routines: [{ id: 1, name: "Morning Brief", trigger_phrase: "morning brief", steps: [], enabled: true }]
        })
      );
    }
    if (url.endsWith("/api/recall")) {
      return new Response(JSON.stringify({ events: [] }));
    }
    if (url.endsWith("/api/recall/status")) {
      return new Response(JSON.stringify({ recall_enabled: false }));
    }
    if (url.endsWith("/api/timers") && init?.method === "POST") {
      return new Response(JSON.stringify({ scheduled: true, label: "Standup", delay_sec: 300 }));
    }
    if (url.endsWith("/api/voice/status")) {
      return new Response(
        JSON.stringify({
          wake_word: "hey_jarvis",
          listening: false,
          speaking: false,
          dictation_mode: false
        })
      );
    }
    if (url.endsWith("/api/chat") && init?.method === "POST") {
      return new Response(
        JSON.stringify({
          conversation_id: "default",
          reply: "Systems verified at zero cost.",
          model_id: "nemotron-3.5-lightning-free",
          provider_id: "opencode",
          lane: "fast",
          cost: 0,
          tokens_in: 120,
          tokens_out: 18,
          latency_ms: 285,
          shifted_from: "iceman-free",
          shift_reason: "402 quota exhausted",
          extracted_facts: [],
          tool_calls: []
        })
      );
    }
    return new Response(JSON.stringify({}));
  });
}

describe("KODA Spatial Command Deck", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", mockApiFetch());
  });

  it("renders $0 OpenCode Router matrix, pending HITL approval card, and submits chat", async () => {
    render(<App />);

    const modelMatches = await screen.findAllByText(/nemotron-3.5-lightning-free/i);
    expect(modelMatches.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/\$0\.00 HARD CAP/i)).toBeInTheDocument();
    expect(screen.getByText(/Execute shell command/i)).toBeInTheDocument();

    // Approve pending Tier-3 HITL request
    fireEvent.click(screen.getByRole("button", { name: /Approve action/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Execute shell command/i)).not.toBeInTheDocument();
    });

    // Submit prompt in Omnibar and verify failover notice pill + assistant message
    const input = screen.getByLabelText(/Command Koda/i);
    fireEvent.change(input, { target: { value: "Verify telemetry status" } });
    fireEvent.click(screen.getByRole("button", { name: /Send command/i }));

    expect(await screen.findByText(/Systems verified at zero cost\./i)).toBeInTheDocument();
    expect(screen.getByText(/Failover: iceman-free/i)).toBeInTheDocument();

    // Switch telemetry tabs
    fireEvent.click(screen.getByRole("tab", { name: /Memory/i }));
    expect(await screen.findByText(/Karthikeya/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Tools & MCP/i }));
    expect(await screen.findByText(/system_metrics/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Proactive/i }));
    expect(await screen.findByText(/Daily Morning Briefing/i)).toBeInTheDocument();
  });
});
