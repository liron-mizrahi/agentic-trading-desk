import { create } from "zustand";
import type { Trade, WebSocketEvent, WsStatus } from "./types";

const MAX_EVENTS = 50;

export interface AnalysisData {
  ticker: string;
  analysis: {
    id: string;
    ticker: string;
    step1_passed: boolean | null;
    step2_passed: boolean | null;
    step3_passed: boolean | null;
    rsi2: number | null;
    chop: number | null;
    sma200: number | null;
    price: number | null;
    raw_llm_reasoning: string | null;
    llm_decision: string | null;
    llm_confidence: number | null;
    error_message: string | null;
    dead_letter: boolean;
    retry_count: number;
    created_at: string | null;
  };
  trade: Record<string, unknown> | null;
}

export interface TradingStore {
  trades: Trade[];
  events: WebSocketEvent[];
  wsStatus: WsStatus;
  loading: boolean;
  error: string | null;

  // Pipeline results
  activeTicker: string | null;
  analysisResult: AnalysisData | null;
  analysisLoading: boolean;
  analysisError: string | null;

  pendingTrades: () => Trade[];

  addTrade: (trade: Trade) => void;
  updateTrade: (tradeId: string, updates: Partial<Trade>) => void;
  addEvent: (event: WebSocketEvent) => void;
  setWsStatus: (status: WsStatus) => void;
  fetchPendingTrades: () => Promise<void>;
  approveTrade: (tradeId: string) => Promise<void>;
  rejectTrade: (tradeId: string) => Promise<void>;
  analyzeTicker: (ticker: string) => Promise<void>;
  fetchAnalysis: (ticker: string) => Promise<void>;
  clearError: () => void;
}

export const useTradingStore = create<TradingStore>((set, get) => ({
  trades: [],
  events: [],
  wsStatus: "disconnected",
  loading: false,
  error: null,
  activeTicker: null,
  analysisResult: null,
  analysisLoading: false,
  analysisError: null,

  pendingTrades: () => get().trades.filter((t) => t.status === "PENDING"),

  addTrade: (trade) => set((s) => ({ trades: [...s.trades, trade] })),
  updateTrade: (tradeId, updates) => set((s) => ({ trades: s.trades.map((t) => t.id === tradeId ? { ...t, ...updates } : t) })),
  addEvent: (event) => set((s) => ({ events: [{ ...event, id: event.id || crypto.randomUUID() }, ...s.events].slice(0, MAX_EVENTS) })),
  setWsStatus: (status) => set({ wsStatus: status }),
  clearError: () => set({ error: null }),

  fetchPendingTrades: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch("/api/v1/trades/pending");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      set({ trades: await res.json(), loading: false });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Failed to fetch", loading: false });
    }
  },

  approveTrade: async (tradeId) => {
    const prev = get().trades.find((t) => t.id === tradeId);
    get().updateTrade(tradeId, { status: "APPROVED" });
    try {
      await fetch(`/api/v1/trades/${tradeId}/action`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "approve" }) });
    } catch {
      if (prev) get().updateTrade(tradeId, { status: prev.status });
    }
  },

  rejectTrade: async (tradeId) => {
    const prev = get().trades.find((t) => t.id === tradeId);
    get().updateTrade(tradeId, { status: "REJECTED" });
    try {
      await fetch(`/api/v1/trades/${tradeId}/action`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "reject" }) });
    } catch {
      if (prev) get().updateTrade(tradeId, { status: prev.status });
    }
  },

  analyzeTicker: async (ticker) => {
    set({ activeTicker: ticker, analysisLoading: true, analysisError: null, analysisResult: null });
    try {
      const res = await fetch("/api/v1/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker }) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Poll for results
      let attempts = 0;
      while (attempts < 30) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const ar = await fetch(`/api/v1/analysis/${ticker}`);
          if (ar.ok) {
            const data = await ar.json();
            set({ analysisResult: data, analysisLoading: false });
            return;
          }
        } catch {}
        attempts++;
      }
      set({ analysisError: "Timed out waiting for analysis", analysisLoading: false });
    } catch (err) {
      set({ analysisError: err instanceof Error ? err.message : "Analysis failed", analysisLoading: false });
    }
  },

  fetchAnalysis: async (ticker) => {
    set({ analysisLoading: true, analysisError: null });
    try {
      const res = await fetch(`/api/v1/analysis/${ticker}`);
      if (res.status === 404) { set({ analysisResult: null, analysisLoading: false }); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      set({ analysisResult: await res.json(), analysisLoading: false });
    } catch (err) {
      set({ analysisError: err instanceof Error ? err.message : "Failed to fetch analysis", analysisLoading: false });
    }
  },
}));
