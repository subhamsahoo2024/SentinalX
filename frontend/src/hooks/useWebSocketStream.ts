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

function closeSocketSafely(ws: WebSocket | null) {
  if (!ws) return;
  ws.onopen = null;
  ws.onmessage = null;
  ws.onerror = null;
  ws.onclose = null;
  if (ws.readyState === WebSocket.CONNECTING) {
    ws.onopen = () => {
      ws.close(1000, 'Component unmounted');
    };
  } else if (ws.readyState === WebSocket.OPEN) {
    ws.close(1000, 'Component unmounted');
  }
}

export function useWebSocketStream<T = unknown>(
  path: string,
  onMessage?: (msg: T) => void
): UseWebSocketStreamResult<T> {
  const [status, setStatus] = useState<WebSocketConnectionStatus>('connecting');
  const [lastMessage, setLastMessage] = useState<T | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const connectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
      closeSocketSafely(socketRef.current);
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
          ws.close(1000, 'Component unmounted');
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
        if (!isMountedRef.current) return;
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

    // Defer initial connection by one macrotask so React StrictMode's
    // immediate mount -> unmount -> remount cycle doesn't abort a CONNECTING socket.
    connectTimerRef.current = setTimeout(() => {
      connectTimerRef.current = null;
      if (isMountedRef.current) {
        connect();
      }
    }, 0);

    return () => {
      isMountedRef.current = false;
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
        connectTimerRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        closeSocketSafely(socketRef.current);
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
