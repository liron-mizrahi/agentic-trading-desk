"use client";

import { useEffect, useRef, useCallback } from "react";
import { useTradingStore } from "@/store";
import type { WebSocketEvent } from "@/store/types";

// WebSocket URL uses the same host as the page, port 8000 for the backend
function getWsUrl(): string {
  if (typeof window === "undefined") return "ws://localhost:8000/ws/notifications";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.hostname}:8000/ws/notifications`;
}

const INITIAL_RETRY_DELAY = 1_000;
const MAX_RETRY_DELAY = 30_000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const addEvent = useTradingStore((s) => s.addEvent);
  const setWsStatus = useTradingStore((s) => s.setWsStatus);
  const fetchPendingTrades = useTradingStore((s) => s.fetchPendingTrades);

  const addEventRef = useRef(addEvent);
  const setWsStatusRef = useRef(setWsStatus);
  const fetchPendingRef = useRef(fetchPendingTrades);

  addEventRef.current = addEvent;
  setWsStatusRef.current = setWsStatus;
  fetchPendingRef.current = fetchPendingTrades;

  const connectRef = useRef<() => void>();

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = retryDelayRef.current;
    retryDelayRef.current = Math.min(retryDelayRef.current * 2, MAX_RETRY_DELAY);
    retryTimerRef.current = setTimeout(() => {
      if (mountedRef.current && connectRef.current) connectRef.current();
    }, delay);
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setWsStatusRef.current("connecting");

    const ws = new WebSocket(getWsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setWsStatusRef.current("connected");
      retryDelayRef.current = INITIAL_RETRY_DELAY;
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const parsed: WebSocketEvent = JSON.parse(event.data);
        addEventRef.current(parsed);

        switch (parsed.event) {
          case "NEW_TRADE":
            // Refresh pending trades when a new proposal arrives
            fetchPendingRef.current();
            break;
          case "TRADE_UPDATED":
            // Refresh after execution/rejection
            fetchPendingRef.current();
            break;
          case "SYSTEM_WARNING":
          case "CONNECTION_OK":
            break;
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setWsStatusRef.current("disconnected");
      wsRef.current = null;
      scheduleReconnect();
    };

    ws.onerror = () => ws.close();
  }, [scheduleReconnect]);

  connectRef.current = connect;

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {};
}
