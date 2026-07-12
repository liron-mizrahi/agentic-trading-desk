"use client";

import { useMemo } from "react";
import { useTradingStore } from "@/store";
import { Clock, AlertTriangle, CheckCircle, TrendingUp } from "lucide-react";
import clsx from "clsx";
import type { WebSocketEvent, WebSocketEventType, WsStatus } from "@/store/types";

// ─── Helpers ────────────────────────────────────────────────────────

function eventIcon(type: WebSocketEventType) {
  switch (type) {
    case "NEW_TRADE":
      return TrendingUp;
    case "TRADE_UPDATED":
      return CheckCircle;
    case "SYSTEM_WARNING":
      return AlertTriangle;
    case "CONNECTION_OK":
      return CheckCircle;
  }
}

function eventColor(type: WebSocketEventType) {
  switch (type) {
    case "NEW_TRADE":
      return "text-accent-green";
    case "TRADE_UPDATED":
      return "text-accent-blue";
    case "SYSTEM_WARNING":
      return "text-accent-yellow";
    case "CONNECTION_OK":
      return "text-accent-green";
  }
}

function wsIndicator(status: WsStatus) {
  switch (status) {
    case "connected":
      return "bg-accent-green";
    case "connecting":
      return "bg-accent-yellow";
    case "disconnected":
      return "bg-accent-red";
  }
}

function formatTimestamp(ts: string) {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "--:--:--";
  }
}

// ─── LiveTickerTape ──────────────────────────────────────────────────

interface LiveTickerTapeProps {
  onToggleLog?: () => void;
}

export function LiveTickerTape({ onToggleLog }: LiveTickerTapeProps) {
  const events = useTradingStore((s) => s.events);
  const wsStatus = useTradingStore((s) => s.wsStatus);

  const latest = useMemo(() => events.slice(0, 5), [events]);

  return (
    <div className="card flex items-center gap-3 overflow-hidden py-2">
      {/* Connection status dot */}
      <button
        onClick={onToggleLog}
        className="flex shrink-0 items-center gap-2 rounded px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-elevated transition-colors"
        title={`WebSocket: ${wsStatus}`}
      >
        <span
          className={clsx(
            "inline-block h-2.5 w-2.5 rounded-full",
            wsIndicator(wsStatus),
            wsStatus === "connecting" && "animate-pulse-dot",
          )}
        />
        <span className="hidden sm:inline">
          {wsStatus === "connected"
            ? "Live"
            : wsStatus === "connecting"
              ? "Connecting…"
              : "Offline"}
        </span>
      </button>

      {/* Ticker tape */}
      <div className="ticker-container flex-1">
        {latest.length === 0 ? (
          <span className="text-sm text-text-muted">
            {wsStatus === "connected"
              ? "Waiting for events…"
              : "No connection"}
          </span>
        ) : (
          <div className="ticker-content flex items-center gap-6">
            {latest.map((evt) => {
              const Icon = eventIcon(evt.event);
              return (
                <span
                  key={evt.id}
                  className="flex items-center gap-2 text-sm whitespace-nowrap"
                >
                  <Icon className={clsx("h-3.5 w-3.5", eventColor(evt.event))} />
                  <span className="text-text-muted">
                    {formatTimestamp(evt.timestamp || "")}
                  </span>
                  <span className="text-text-primary">{evt.message}</span>
                </span>
              );
            })}
          </div>
        )}
      </div>

      {/* Event count badge */}
      <span className="shrink-0 rounded bg-surface-elevated px-2 py-0.5 text-xs text-text-muted">
        {events.length}
      </span>
    </div>
  );
}

// ─── EventLogOverlay ─────────────────────────────────────────────────

interface EventLogOverlayProps {
  open: boolean;
  onClose: () => void;
}

export function EventLogOverlay({ open, onClose }: EventLogOverlayProps) {
  const events = useTradingStore((s) => s.events);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-12">
      <div className="card mx-4 w-full max-w-lg max-h-[70vh] overflow-y-auto">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">
            Event Log
          </h3>
          <button
            onClick={onClose}
            className="rounded p-1 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors"
          >
            <Clock className="h-4 w-4" />
          </button>
        </div>
        {events.length === 0 ? (
          <p className="py-4 text-center text-sm text-text-muted">
            No events recorded yet.
          </p>
        ) : (
          <ul className="space-y-1">
            {events.map((evt) => {
              const Icon = eventIcon(evt.event);
              return (
                <li
                  key={evt.id}
                  className="flex items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-elevated"
                >
                  <Icon
                    className={clsx(
                      "mt-0.5 h-3.5 w-3.5 shrink-0",
                      eventColor(evt.event),
                    )}
                  />
                  <span className="text-text-muted shrink-0">
                    {formatTimestamp(evt.timestamp || "")}
                  </span>
                  <span className="text-text-primary">{evt.message}</span>
                  {evt.trade_id && (
                    <span className="ml-auto shrink-0 rounded bg-surface-elevated px-1.5 py-0.5 text-xs text-text-muted">
                      {evt.trade_id.slice(0, 8)}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
