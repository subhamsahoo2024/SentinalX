'use client';

import { Suspense, useState } from 'react';
import { Header } from '@/components/Header';
import { Sidebar } from '@/components/Sidebar';
import { ApprovalModal } from '@/components/governance/ApprovalModal';
import { useIsMobile } from '@/hooks/use-mobile';

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
    <div className="flex min-h-screen w-full bg-[#F5F9FF] dark:bg-[#030A17] transition-colors duration-150">
      <Suspense fallback={<aside className="w-64 shrink-0 bg-[#041533] dark:bg-[#040B18] border-r border-[#112A56]" />}>
        <Sidebar
          isOpen={sidebarOpen}
          isMobile={isMobile}
          onClose={handleClose}
        />
      </Suspense>

      <div className="flex flex-1 flex-col min-w-0">
        <Suspense fallback={<header className="h-14 border-b border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shrink-0" />}>
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

      <ApprovalModal />
    </div>
  );
}

