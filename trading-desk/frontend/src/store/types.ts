// ─── Type Definitions (matches backend/app/schemas.py) ──────────────

export interface Trade {
  id: string;
  ticker: string;
  strategy: string;
  decision: string | null;
  confidence: number | null;
  reasoning: string | null;
  proposed_price: number | null;
  position_size: number | null;
  position_size_pct: number | null;
  exit_condition: string | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward_ratio: number | null;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXECUTED" | "FAILED" | "EXPIRED";
  rsi_2_value: number | null;
  chop_value: number | null;
  sma_200_value: number | null;
  sector: string | null;
  human_feedback: string | null;
  analysis_logs: AnalysisLog[] | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AnalysisLog {
  id: string;
  trade_id: string | null;
  ticker: string;
  step1_passed: boolean | null;
  step2_passed: boolean | null;
  step3_passed: boolean | null;
  rsi2: number | null;
  chop: number | null;
  sma200: number | null;
  price: number | null;
  raw_llm_reasoning: string | null;
  technical_data: Record<string, unknown> | null;
  news_context: Record<string, unknown> | null;
  llm_decision: string | null;
  llm_confidence: number | null;
  error_message: string | null;
  retry_count: number;
  dead_letter: boolean;
  created_at: string | null;
}

export type WebSocketEventType =
  | "NEW_TRADE"
  | "TRADE_UPDATED"
  | "SYSTEM_WARNING"
  | "CONNECTION_OK";

export interface WebSocketEvent {
  id: string;
  event: WebSocketEventType;
  message?: string;
  trade_id?: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

export type WsStatus = "connecting" | "connected" | "disconnected";
