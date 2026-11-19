'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type WebSocketConnectionStatus = 'connecting' | 'connected' | 'disconnected';

export interface UseWebSocketStreamResult<T> {
  status: WebSocketConnectionStatus;
  lastMessage: T | null;
  sendMessage: (message: unknown) => void;
  reconnect: () => void;
}

const WS_BASE_URL = (
  process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8000'
).replace(/\/+$/, '');

export function useWebSocketStream<T = unknown>(
  path: string,
  onMessage?: (msg: T) => void
): UseWebSocketStreamResult<T> {
  const [status, setStatus] = useState<WebSocketConnectionStatus>('connecting');
  const [lastMessage, setLastMessage] = useState<T | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const backoffRef = useRef<number>(1000);
  const isMountedRef = useRef<boolean>(true);
  const onMessageRef = useRef(onMessage);
  const connectRef = useRef<() => void>(() => {});

  // Keep latest onMessage callback in ref to prevent reconnect loops on re-renders
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (socketRef.current) {
      socketRef.current.onopen = null;
      socketRef.current.onclose = null;
      socketRef.current.onerror = null;
      socketRef.current.onmessage = null;
      socketRef.current.close();
      socketRef.current = null;
    }

    if (!isMountedRef.current) return;

    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const targetUrl = `${WS_BASE_URL}${cleanPath}`;

    try {
      const ws = new WebSocket(targetUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) {
          ws.close();
          return;
        }
        setStatus('connected');
        backoffRef.current = 1000;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!isMountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data) as T;
          setLastMessage(parsed);
          onMessageRef.current?.(parsed);
        } catch (err) {
          console.warn('Failed to parse WebSocket JSON message:', err);
        }
      };

      ws.onerror = (err) => {
        console.warn(`WebSocket error on ${targetUrl}:`, err);
      };

      ws.onclose = (event) => {
        if (!isMountedRef.current) return;

        setStatus('disconnected');
        socketRef.current = null;

        if (event.code === 1000) return;

        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 10000);

        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            setStatus('connecting');
            connectRef.current();
          }
        }, delay);
      };
    } catch (err) {
      console.warn('Failed to create WebSocket instance:', err);
      const delay = backoffRef.current;
      backoffRef.current = Math.min(delay * 2, 10000);
      reconnectTimeoutRef.current = setTimeout(() => {
        if (isMountedRef.current) {
          setStatus('disconnected');
          connectRef.current();
        }
      }, delay);
    }
  }, [path]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close(1000, 'Component unmounted');
        socketRef.current = null;
      }
    };
  }, [connect]);

  const sendMessage = useCallback((message: unknown) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const payload = typeof message === 'string' ? message : JSON.stringify(message);
      socketRef.current.send(payload);
    } else {
      console.warn('Cannot send message: WebSocket is not open');
    }
  }, []);

  const reconnect = useCallback(() => {
    setStatus('connecting');
    backoffRef.current = 1000;
    connect();
  }, [connect]);

  return {
    status,
    lastMessage,
    sendMessage,
    reconnect,
  };
}
