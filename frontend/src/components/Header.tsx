'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Moon, PanelLeftClose, PanelLeftOpen, Sun } from 'lucide-react';
import { LiveConnectionBadge } from '@/components/LiveConnectionBadge';
import { UserSessionMenu } from '@/components/governance/UserSessionMenu';
import { LaunchScenarioModal } from '@/components/simulator/LaunchScenarioModal';
import { useTheme } from '@/hooks/use-theme';
import { ASSETS } from '@/lib/assets';

function resolveTitle(pathname: string): string {
  if (pathname === '/') return 'Fleet Overview';
  if (pathname.startsWith('/approvals')) return 'Governance & Approvals';
  if (pathname.startsWith('/costs')) return 'Cost & Token Attribution';
  if (pathname.startsWith('/policies')) return 'Governance Policies';
  if (pathname.startsWith('/runs/')) return 'Run Execution Detail';
  return 'Control Tower';
}

interface HeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function Header({ sidebarOpen, onToggleSidebar }: HeaderProps) {
  const pathname = usePathname();
  const title = resolveTitle(pathname);
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] px-4 sm:px-6 shrink-0 transition-colors duration-150">
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-expanded={sidebarOpen}
          aria-label={sidebarOpen ? 'Close navigation sidebar' : 'Open navigation sidebar'}
          title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] text-[#061838] dark:text-slate-200 hover:bg-[#EFF6FF] dark:hover:bg-[#102650] hover:border-[#0257D5]/40 dark:hover:border-[#00C2FF]/50 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0257D5] dark:focus-visible:ring-[#00C2FF]"
        >
          {sidebarOpen ? (
            <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
          ) : (
            <PanelLeftOpen className="h-4 w-4 text-[#0257D5] dark:text-[#00C2FF]" aria-hidden="true" />
          )}
        </button>

        {!sidebarOpen && (
          <Link
            href="/"
            className="flex items-center gap-2 pr-2 border-r border-[#D4E2F4] dark:border-[#172E56] shrink-0"
          >
            <Image
              src={isDark ? ASSETS.logoDark : ASSETS.logoLight}
              alt="Sentinel-X logo"
              width={24}
              height={24}
              referrerPolicy="no-referrer"
              className="h-6 w-6 object-contain rounded"
            />
            <span className="hidden sm:inline text-xs font-semibold tracking-tight text-[#041533] dark:text-white whitespace-nowrap">
              SENTINEL-X
            </span>
          </Link>
        )}

        <h1 className="text-sm font-semibold text-[#061838] dark:text-slate-100 truncate whitespace-nowrap">
          {title}
        </h1>
      </div>

      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        <LaunchScenarioModal />
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2.5 py-1.5 text-xs font-medium text-[#061838] dark:text-slate-200 hover:bg-[#EFF6FF] dark:hover:bg-[#102650] transition-colors whitespace-nowrap shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0257D5] dark:focus-visible:ring-[#00C2FF]"
        >
          {isDark ? (
            <>
              <Sun className="h-3.5 w-3.5 text-[#00C2FF]" aria-hidden="true" />
              <span className="hidden md:inline">Light</span>
            </>
          ) : (
            <>
              <Moon className="h-3.5 w-3.5 text-[#0257D5]" aria-hidden="true" />
              <span className="hidden md:inline">Dark</span>
            </>
          )}
        </button>
        <LiveConnectionBadge />
        <UserSessionMenu />
      </div>
    </header>
  );
}
