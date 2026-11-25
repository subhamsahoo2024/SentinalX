'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  DollarSign,
  FileText,
  PanelLeftClose,
  ShieldCheck,
} from 'lucide-react';
import { useApprovals } from '@/components/governance/ApprovalContext';
import { useTheme } from '@/hooks/use-theme';
import { ASSETS } from '@/lib/assets';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { href: '/', label: 'Fleet Overview', icon: Activity },
  { href: '/approvals', label: 'Approvals', icon: ShieldCheck, showBadge: true },
  { href: '/costs', label: 'Cost Attribution', icon: DollarSign },
  { href: '/policies', label: 'Policies', icon: FileText },
];

interface SidebarProps {
  isOpen: boolean;
  isMobile: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, isMobile, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { pendingCount } = useApprovals();
  const { isDark } = useTheme();

  const handleNavClick = () => {
    if (isMobile) {
      onClose();
    }
  };

  return (
    <>
      {isMobile && isOpen && (
        <div
          className="fixed inset-0 z-30 bg-[#041533]/60 dark:bg-black/70 backdrop-blur-[1px]"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        aria-hidden={!isOpen}
        className={cn(
          'shrink-0 bg-[#041533] dark:bg-[#040B18] text-slate-200 flex flex-col border-r border-[#112A56] dark:border-[#15284B] transition-[width,transform] duration-200 ease-out overflow-hidden',
          isMobile
            ? cn(
                'fixed inset-y-0 left-0 z-40 w-64 shadow-2xl',
                isOpen ? 'translate-x-0' : '-translate-x-full',
              )
            : isOpen
              ? 'w-64'
              : 'w-0 border-r-0',
        )}
      >
        <div className="w-64 flex flex-col h-full">
          <div className="px-4 py-4 border-b border-[#112A56] dark:border-[#15284B] flex items-center justify-between gap-2">
            <Link
              href="/"
              onClick={handleNavClick}
              className="flex items-center gap-2.5 min-w-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00D4FF] rounded-md"
            >
              <div
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-lg p-1 shadow-sm shrink-0 transition-colors',
                  isDark
                    ? 'bg-[#030A17] border border-[#172E56]'
                    : 'bg-white',
                )}
              >
                <Image
                  src={isDark ? ASSETS.logoDark : ASSETS.logoLight}
                  alt="Sentinel-X logo"
                  width={28}
                  height={28}
                  referrerPolicy="no-referrer"
                  className="h-7 w-7 object-contain"
                />
              </div>
              <div className="min-w-0">
                <span className="block text-sm font-semibold tracking-tight text-white whitespace-nowrap">
                  SENTINEL-X
                </span>
                <span className="block text-[11px] text-[#7DD3FC] whitespace-nowrap">
                  Control Tower
                </span>
              </div>
            </Link>

            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-slate-300 hover:bg-[#0D2856] hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00D4FF]"
              aria-label="Close sidebar"
              title="Close sidebar"
            >
              <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          <nav className="flex-1 px-3 py-4 space-y-1" aria-label="Primary Navigation">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.href === '/'
                  ? pathname === '/' || pathname.startsWith('/runs')
                  : pathname.startsWith(item.href);
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={handleNavClick}
                  tabIndex={isOpen ? 0 : -1}
                  className={cn(
                    'flex items-center justify-between rounded-md px-3 py-2.5 text-sm font-medium transition-colors whitespace-nowrap',
                    isActive
                      ? 'bg-[#0257D5]/30 text-white border border-[#00C2FF]/35'
                      : 'text-slate-300 border border-transparent hover:bg-[#0B224B] hover:text-white',
                  )}
                >
                  <span className="flex items-center gap-2.5 min-w-0">
                    <Icon
                      className={cn(
                        'h-4 w-4 shrink-0',
                        isActive ? 'text-[#00D4FF]' : 'text-slate-400',
                      )}
                      aria-hidden="true"
                    />
                    <span className="truncate">{item.label}</span>
                  </span>
                  {item.showBadge && pendingCount > 0 && (
                    <span className="ml-2 inline-flex items-center justify-center rounded-md bg-amber-500 px-1.5 py-0.5 text-[11px] font-mono font-semibold text-slate-950 tabular-nums">
                      {pendingCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="border-t border-[#112A56] dark:border-[#15284B] px-5 py-4 text-xs text-slate-400">
            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className="text-[#7DD3FC]">v1.0.0</span>
              <span className="text-slate-400">LOCAL / DEV</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
