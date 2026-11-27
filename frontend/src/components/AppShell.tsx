'use client';

import { Suspense, useEffect, useState, useSyncExternalStore } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Header } from '@/components/Header';
import { Sidebar } from '@/components/Sidebar';
import { ApprovalProvider } from '@/components/governance/ApprovalContext';
import { ApprovalModal } from '@/components/governance/ApprovalModal';
import { useIsClient } from '@/hooks/use-is-client';
import { useIsMobile } from '@/hooks/use-mobile';
import { verifyCurrentSession } from '@/lib/api';
import {
  TOKEN_KEY,
  USER_KEY,
  clearAuthSession,
  getAuthTokenSnapshot,
  getTokenExpirationMs,
  isTokenExpired,
  subscribeAuth,
} from '@/lib/auth';

function AuthGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const isClient = useIsClient();
  const token = useSyncExternalStore(
    subscribeAuth,
    getAuthTokenSnapshot,
    () => null,
  );

  useEffect(() => {
    if (!isClient) return;

    if (!token) {
      if (
        window.localStorage.getItem(TOKEN_KEY) ||
        window.localStorage.getItem(USER_KEY)
      ) {
        clearAuthSession();
      }
      if (pathname !== '/login') {
        router.replace('/login');
      }
      return;
    }

    let cancelled = false;
    void verifyCurrentSession().then((valid) => {
      if (!cancelled && !valid && pathname !== '/login') {
        router.replace('/login');
      }
    });

    const expMs = getTokenExpirationMs(token);
    const delayMs = expMs !== null ? Math.max(0, expMs - Date.now()) : 0;
    const expiryTimer =
      expMs !== null && delayMs <= 2_147_483_647
        ? setTimeout(() => {
            clearAuthSession();
          }, delayMs)
        : null;

    const handleVisibilityOrFocus = () => {
      if (isTokenExpired(token)) {
        clearAuthSession();
      }
    };
    window.addEventListener('focus', handleVisibilityOrFocus);
    document.addEventListener('visibilitychange', handleVisibilityOrFocus);

    return () => {
      cancelled = true;
      if (expiryTimer !== null) {
        clearTimeout(expiryTimer);
      }
      window.removeEventListener('focus', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
    };
  }, [isClient, token, pathname, router]);

  return null;
}

function AuthOverlay() {
  const pathname = usePathname();
  const isClient = useIsClient();
  const token = useSyncExternalStore(
    subscribeAuth,
    getAuthTokenSnapshot,
    () => null,
  );

  if (pathname === '/login' || (isClient && Boolean(token))) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-[#F5F9FF] dark:bg-[#030A17]"
      aria-hidden="true"
    />
  );
}

function ApprovalModalGate() {
  const pathname = usePathname();
  if (pathname === '/login') {
    return null;
  }
  return <ApprovalModal />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const isMobile = useIsMobile();
  const [desktopOpen, setDesktopOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);

  const sidebarOpen = isMobile ? mobileOpen : desktopOpen;

  const handleClose = () => {
    if (isMobile) {
      setMobileOpen(false);
    } else {
      setDesktopOpen(false);
    }
  };

  const handleToggle = () => {
    if (isMobile) {
      setMobileOpen((prev) => !prev);
    } else {
      setDesktopOpen((prev) => !prev);
    }
  };

  return (
    <ApprovalProvider>
      <Suspense fallback={null}>
        <AuthGuard />
      </Suspense>
      <Suspense fallback={null}>
        <AuthOverlay />
      </Suspense>

      <div className="flex min-h-screen w-full bg-[#F5F9FF] dark:bg-[#030A17] transition-colors duration-150">
        <Suspense
          fallback={
            <aside className="w-64 shrink-0 bg-[#041533] dark:bg-[#040B18] border-r border-[#112A56]" />
          }
        >
          <Sidebar
            isOpen={sidebarOpen}
            isMobile={isMobile}
            onClose={handleClose}
          />
        </Suspense>

        <div className="flex flex-1 flex-col min-w-0">
          <Suspense
            fallback={
              <header className="h-14 border-b border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shrink-0" />
            }
          >
            <Header
              sidebarOpen={sidebarOpen}
              onToggleSidebar={handleToggle}
            />
          </Suspense>
          <main className="flex-1 overflow-y-auto p-6">
            <Suspense
              fallback={
                <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-8 text-xs text-slate-500 dark:text-slate-400">
                  Loading workspace view...
                </div>
              }
            >
              {children}
            </Suspense>
          </main>
        </div>

        <Suspense fallback={null}>
          <ApprovalModalGate />
        </Suspense>
      </div>
    </ApprovalProvider>
  );
}
