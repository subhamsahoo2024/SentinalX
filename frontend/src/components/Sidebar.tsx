'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  ShieldAlert,
  Coins,
  Shield,
  Sliders,
} from 'lucide-react';
import { useApprovals } from '@/components/governance/ApprovalContext';

interface NavItem {
  name: string;
  href: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  {
    name: 'Fleet Overview',
    href: '/',
    icon: LayoutDashboard,
    exact: true,
  },
  {
    name: 'Approvals',
    href: '/approvals',
    icon: ShieldAlert,
  },
  {
    name: 'Cost Attribution',
    href: '/costs',
    icon: Coins,
  },
  {
    name: 'Policies',
    href: '/policies',
    icon: Sliders,
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { pendingCount } = useApprovals();

  const isLinkActive = (item: NavItem) => {
    if (item.exact) {
      return pathname === item.href;
    }
    return pathname.startsWith(item.href);
  };

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/70 backdrop-blur-md flex flex-col justify-between shrink-0 select-none">
      <div className="flex flex-col">
        {/* Brand Header */}
        <div className="h-16 px-5 border-b border-slate-800 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded-lg bg-cyan-950/80 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-sm shadow-cyan-950 group-hover:border-cyan-400 transition-colors">
              <Shield className="w-5 h-5 fill-cyan-950/40 stroke-cyan-400" />
            </div>
            <div>
              <div className="flex items-center font-bold tracking-tight text-slate-100 text-base leading-none">
                SENTINEL<span className="text-cyan-400 ml-0.5">X</span>
              </div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 mt-1">
                Control Tower
              </div>
            </div>
          </Link>
        </div>

        {/* Section Label */}
        <div className="px-5 pt-6 pb-2 text-[10px] font-mono uppercase tracking-wider text-slate-400">
          Navigation
        </div>

        {/* Nav Links */}
        <nav className="px-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const active = isLinkActive(item);
            const Icon = item.icon;
            const hasPendingApprovals = item.href === '/approvals' && pendingCount > 0;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 shadow-sm shadow-cyan-950/50'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 border border-transparent'
                }`}
              >
                <Icon
                  className={`w-4 h-4 ${
                    active ? 'text-cyan-400' : 'text-slate-400'
                  }`}
                />
                <span>{item.name}</span>
                {hasPendingApprovals && (
                  <span className="ml-auto px-2 py-0.5 text-[11px] font-mono font-bold rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">
                    {pendingCount}
                  </span>
                )}
                {active && !hasPendingApprovals && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-sm shadow-cyan-400" />
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Sidebar Footer */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/40">
        <div className="flex items-center justify-between text-xs text-slate-400 font-mono mb-2">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            SYSTEM
          </span>
          <span className="text-slate-400">v1.0.0</span>
        </div>
        <div className="flex items-center justify-between text-[11px] text-slate-400 bg-slate-900/80 border border-slate-800 rounded px-2.5 py-1.5">
          <span className="text-slate-400">ENV</span>
          <span className="font-mono text-cyan-400/90 font-medium">LOCAL / DEV</span>
        </div>
      </div>
    </aside>
  );
}
