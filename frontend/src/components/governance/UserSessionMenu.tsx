'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ChevronDown, LogOut, ShieldCheck, UserCheck } from 'lucide-react';
import {
  AUTH_CHANGED_EVENT,
  DEMO_ACCOUNTS,
  getStoredUser,
  loginWithCredentials,
  signOutUser,
  USER_KEY,
} from '@/lib/auth';
import { cn } from '@/lib/utils';
import type { SentinelUser } from '@/types/telemetry';

let cachedRaw: string | null = null;
let cachedUser: SentinelUser | null = null;

function subscribeAuth(callback: () => void) {
  window.addEventListener(AUTH_CHANGED_EVENT, callback);
  window.addEventListener('storage', callback);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, callback);
    window.removeEventListener('storage', callback);
  };
}

function getAuthSnapshot(): SentinelUser | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(USER_KEY) ?? '__default__';
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedUser = getStoredUser();
  }
  return cachedUser;
}

export function UserSessionMenu() {
  const user = useSyncExternalStore(subscribeAuth, getAuthSnapshot, () => null);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleOutside);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [open]);

  const handleDemoSwitch = async (demoEmail: string) => {
    setLoading(true);
    setError(null);
    try {
      await loginWithCredentials(demoEmail, 'sentinel123');
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to switch demo account');
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError(null);
    try {
      await loginWithCredentials(email, password);
      setEmail('');
      setPassword('');
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-2 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs font-medium text-[#061838] dark:text-slate-100 hover:bg-[#EFF6FF] dark:hover:bg-[#102650] transition-colors whitespace-nowrap shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0257D5] dark:focus-visible:ring-[#00C2FF]"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <UserCheck className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" aria-hidden="true" />
        <span className="max-w-[140px] truncate">
          {user ? user.display_name : 'Sign In / Demo Role'}
        </span>
        {user && (
          <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 border-l border-slate-200 dark:border-[#1D3868] pl-2">
            {user.role}
          </span>
        )}
        <ChevronDown className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Session and RBAC Role Switcher"
          className="absolute right-0 mt-2 w-80 rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-lg z-50 p-4"
        >
          <div className="pb-3 border-b border-slate-200 dark:border-[#172E56]">
            <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">Active Session</p>
            {user ? (
              <div className="mt-1.5 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                    {user.display_name}
                  </p>
                  <p className="text-xs font-mono text-slate-500 dark:text-slate-400 truncate">
                    {user.email}
                  </p>
                </div>
                <span className="rounded border border-[#93C5FD] dark:border-[#00C2FF]/40 bg-[#EFF6FF] dark:bg-[#0257D5]/25 px-2 py-0.5 text-[11px] font-mono font-medium text-[#0257D5] dark:text-[#7DD3FC]">
                  {user.role}
                </span>
              </div>
            ) : (
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Operating with dev headers. Select a signed JWT account below.
              </p>
            )}
          </div>

          <div className="py-3 border-b border-slate-200 dark:border-[#172E56]">
            <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Quick Role Switch
            </p>
            <div className="grid grid-cols-1 gap-1.5">
              {DEMO_ACCOUNTS.map((acct) => {
                const isActive = user?.email?.toLowerCase() === acct.email.toLowerCase();
                return (
                  <button
                    key={acct.user_id}
                    type="button"
                    disabled={loading}
                    onClick={() => void handleDemoSwitch(acct.email)}
                    className={cn(
                      'flex items-center justify-between rounded-md border px-2.5 py-2 text-left text-xs transition-colors disabled:opacity-50',
                      isActive
                        ? 'border-[#0257D5]/40 bg-[#EFF6FF] text-[#041533] dark:border-[#00C2FF]/50 dark:bg-[#0257D5]/25 dark:text-white'
                        : 'border-[#D4E2F4] bg-white text-slate-700 hover:bg-[#F5F9FF] dark:border-[#172E56] dark:bg-[#0A1B3B] dark:text-slate-300 dark:hover:bg-[#102650]',
                    )}
                  >
                    <div className="min-w-0">
                      <span className="font-medium block truncate">{acct.display_name}</span>
                      <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400 block truncate">
                        {acct.email}
                      </span>
                    </div>
                    <span className="ml-2 font-mono text-[11px] font-semibold text-slate-600 dark:text-[#7DD3FC] shrink-0">
                      {acct.role}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <form onSubmit={handleLogin} className="pt-3 space-y-2">
            <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" aria-hidden="true" />
              <span>Credentials Sign In</span>
            </p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="operator@sentinel.local"
              aria-label="Email address"
              className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2.5 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              aria-label="Password"
              className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2.5 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
            />
            {error && <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p>}
            <div className="flex items-center justify-between gap-2 pt-1">
              <button
                type="submit"
                disabled={loading}
                className="rounded-md bg-[#041533] dark:bg-[#0257D5] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#0257D5] dark:hover:bg-[#0346B0] disabled:opacity-50 transition-colors whitespace-nowrap"
              >
                {loading ? 'Signing In...' : 'Sign In'}
              </button>
              {user && (
                <button
                  type="button"
                  onClick={() => {
                    signOutUser();
                    setOpen(false);
                  }}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-[#1D3868] px-2.5 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-[#0D2247] transition-colors whitespace-nowrap"
                >
                  <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Sign Out</span>
                </button>
              )}
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
