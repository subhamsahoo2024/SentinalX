'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { fetchApprovals, submitApprovalDecision } from '@/lib/api';
import { getStoredUser } from '@/lib/auth';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import type { ActorRole, ApprovalDTO, WebSocketMessage } from '@/types/telemetry';

interface ApprovalContextType {
  pendingApprovals: ApprovalDTO[];
  pendingCount: number;
  isLoading: boolean;
  refreshPending: () => Promise<void>;
  decideApproval: (
    approvalId: string,
    decision: 'APPROVED' | 'REJECTED',
    comment?: string,
    role?: ActorRole | string,
  ) => Promise<ApprovalDTO>;
}

const ApprovalContext = createContext<ApprovalContextType | null>(null);

export function ApprovalProvider({ children }: { children: React.ReactNode }) {
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalDTO[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshPending = useCallback(async () => {
    try {
      const data = await fetchApprovals('PENDING');
      setPendingApprovals(data.filter((item) => item.status === 'PENDING'));
    } catch (err) {
      console.warn('Failed to fetch pending approvals:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    fetchApprovals('PENDING')
      .then((data) => {
        if (isMounted) {
          setPendingApprovals(data.filter((item) => item.status === 'PENDING'));
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.warn('Failed to fetch pending approvals:', err);
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleWebSocketMessage = useCallback(
    (msg: WebSocketMessage<unknown>) => {
      if (!msg || typeof msg !== 'object') return;

      if (msg.type === 'APPROVAL_REQUIRED' && msg.data) {
        const newApproval = msg.data as ApprovalDTO;
        if (newApproval && newApproval.approval_id) {
          setPendingApprovals((prev) => {
            const exists = prev.some(
              (a) => a.approval_id === newApproval.approval_id,
            );
            if (exists) {
              return prev.map((a) =>
                a.approval_id === newApproval.approval_id ? newApproval : a,
              );
            }
            return [newApproval, ...prev];
          });
        }
      } else if (
        msg.type === 'APPROVAL_DECIDED' ||
        msg.type === 'FLEET_UPDATED'
      ) {
        const payload = msg.data as Record<string, unknown> | undefined;
        const decidedId =
          (payload?.approval_id as string | undefined) ||
          ((payload?.approval as Record<string, unknown> | undefined)
            ?.approval_id as string | undefined);

        if (decidedId) {
          setPendingApprovals((prev) =>
            prev.filter((a) => a.approval_id !== decidedId),
          );
        } else {
          void refreshPending();
        }
      }
    },
    [refreshPending],
  );

  useWebSocketStream('/ws/fleet', handleWebSocketMessage);

  const decideApproval = useCallback(
    async (
      approvalId: string,
      decision: 'APPROVED' | 'REJECTED',
      comment?: string,
      role?: ActorRole | string,
    ): Promise<ApprovalDTO> => {
      const user = getStoredUser();
      const effectiveRole = role || user?.role || 'approver';
      const actorId = user?.email || `${effectiveRole}@sentinel.local`;
      const updated = await submitApprovalDecision(
        approvalId,
        decision,
        comment ?? '',
        String(effectiveRole),
        actorId,
      );
      setPendingApprovals((prev) =>
        prev.filter((a) => a.approval_id !== approvalId),
      );
      return updated;
    },
    [],
  );

  const value = useMemo(
    () => ({
      pendingApprovals,
      pendingCount: pendingApprovals.length,
      isLoading,
      refreshPending,
      decideApproval,
    }),
    [pendingApprovals, isLoading, refreshPending, decideApproval],
  );

  return (
    <ApprovalContext.Provider value={value}>
      {children}
    </ApprovalContext.Provider>
  );
}

export function useApprovals(): ApprovalContextType {
  const context = useContext(ApprovalContext);
  if (!context) {
    throw new Error('useApprovals must be used within an ApprovalProvider');
  }
  return context;
}
