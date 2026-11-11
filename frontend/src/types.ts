export type KodaStateName =
  | "idle"
  | "listening"
  | "thinking"
  | "shifting"
  | "speaking"
  | "confirm_needed";

export type LaneName = "auto" | "fast" | "vision" | "deep_1m" | "multimodal";

export interface HealthStatus {
  status: string;
  state: KodaStateName;
  allow_paid_models: boolean;
  free_models_count: number;
  opencode_connected: boolean;
}

export interface RouterModelRow {
  id: string;
  provider_id: string;
  input_capabilities: string[];
  tools: boolean;
  state: "HEALTHY" | "SOFT_SHIFTED" | "COOLDOWN" | "HALF_OPEN" | "DISABLED";
  fail_count: number;
  ewma_latency_ms: number;
  total_requests: number;
  total_tokens: number;
  cooldown_until: number;
  last_error: string;
}

export interface RouterShiftItem {
  id: number;
  from_model: string;
  to_model: string;
  reason: string;
  lane: string;
  conversation_id: string;
  created_at: number;
}

export interface RouterStatusResponse {
  allow_paid_models: boolean;
  free_models_count: number;
  models: RouterModelRow[];
  recent_shifts: RouterShiftItem[];
}

export interface PendingApproval {
  id: string;
  tool_name: string;
  args_json: string;
  summary: string;
  tier: string;
  status: string;
  created_at: number;
}

export interface FactItem {
  id: number;
  category: string;
  key: string;
  value: string;
}

export interface ToolItem {
  name: string;
  description: string;
  tier: string;
}

export interface RoutineItem {
  id: number;
  name: string;
  trigger_phrase: string;
  cron_expr: string;
  enabled: boolean;
}

export interface RecallItem {
  id: number;
  app_name: string;
  window_title: string;
  summary_text: string;
  created_at: number;
}

export interface VoiceStatus {
  wake_word: string;
  listening: boolean;
  speaking: boolean;
  dictation_mode: boolean;
}

export interface ChatTimelineMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  model_id?: string;
  lane?: string;
  cost?: number;
  latency_ms?: number;
  shifted_from?: string | null;
  shift_reason?: string | null;
  tool_calls?: Array<{ tool: string; tier: string }>;
}
