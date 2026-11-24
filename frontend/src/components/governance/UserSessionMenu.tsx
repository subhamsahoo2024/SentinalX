'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  ChevronDown,
  KeyRound,
  LogOut,
  Shield,
  ShieldAlert,
  User,
  UserCheck,
} from 'lucide-react';
import {
  clearAuthSession,
  getStoredUser,
  loginWithCredentials,
  SentinelUser,
} from '@/lib/auth';

const DEMO_ACCOUNTS = [
  {
    email: 'approver@sentinel.local',
    name: 'Arjun Mehta',
    role: 'approver',
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  },
  {
    email: 'admin@sentinel.local',
    name: 'Priya Nair',
    role: 'admin',
    badge: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  },
  {
    email: 'operator@sentinel.local',
    name: 'Devika Rao',
    role: 'operator',
    badge: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  },
  {
    email: 'viewer@sentinel.local',
    name: 'Rohan Das',
    role: 'viewer',
    badge: 'bg-slate-800 text-slate-300 border-slate-700',
  },
] as const;

export function getRoleBadgeClass(role?: string): string {
  const norm = (role || '').toLowerCase();
  switch (norm) {
    case 'admin':
      return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
    case 'approver':
      return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
    case 'operator':
      return 'bg-blue-500/20 text-blue-300 border-blue-500/40';
    case 'viewer':
    default:
      return 'bg-slate-800 text-slate-300 border-slate-700';
  }
}

export function UserSessionMenu() {
  const [user, setUser] = useState<SentinelUser | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [emailInput, setEmailInput] = useState('');
  const [passwordInput, setPasswordInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const menuRef = useRef<HTMLDivElement>(null);

  // Sync stored user and listen for cross-tab or in-page auth updates
  useEffect(() => {
    const syncUser = () => {
      setUser(getStoredUser());
    };

    syncUser();

    const handleAuthChange = () => {
      syncUser();
    };

    window.addEventListener('sentinel-auth-changed', handleAuthChange);
    window.addEventListener('storage', handleAuthChange);

    return () => {
      window.removeEventListener('sentinel-auth-changed', handleAuthChange);
      window.removeEventListener('storage', handleAuthChange);
    };
  }, []);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleDemoSwitch = async (email: string) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      await loginWithCredentials(email, 'sentinel123');
      setIsOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleManualLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailInput || !passwordInput) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      await loginWithCredentials(emailInput, passwordInput);
      setEmailInput('');
      setPasswordInput('');
      setIsOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignOut = () => {
    clearAuthSession();
    setIsOpen(false);
  };

  return (
    <div className="relative z-50 font-sans" ref={menuRef}>
      {/* Trigger Button in Header */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 hover:border-slate-600 text-xs text-slate-200 transition-all shadow-sm focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
      >
        <div className="w-5 h-5 rounded-full bg-cyan-950 border border-cyan-500/40 flex items-center justify-center text-cyan-400">
          {user ? (
            <UserCheck className="w-3 h-3 text-emerald-400" />
          ) : (
            <User className="w-3 h-3 text-slate-400" />
          )}
        </div>

        <span className="font-medium text-slate-200 max-w-[130px] truncate">
          {user ? user.display_name : 'Sign In / Demo Role'}
        </span>

        {user && (
          <span
            className={`px-1.5 py-0.2 rounded text-[10px] font-mono font-bold uppercase border ${getRoleBadgeClass(
              user.role
            )}`}
          >
            {user.role}
          </span>
        )}

        <ChevronDown
          className={`w-3.5 h-3.5 text-slate-400 transition-transform ${
            isOpen ? 'rotate-180 text-cyan-400' : ''
          }`}
        />
      </button>

      {/* Popover Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 rounded-xl bg-slate-900/95 border border-slate-700 shadow-2xl backdrop-blur-xl z-50 p-4 space-y-4 animate-in fade-in zoom-in-95 duration-100">
          {/* Active Session Info */}
          <div className="pb-3 border-b border-slate-800">
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1 flex items-center justify-between">
              <span>Active Governance Session</span>
              {user ? (
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  JWT Active
                </span>
              ) : (
                <span className="text-amber-400 font-bold">Dev Headers</span>
              )}
            </div>

            {user ? (
              <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5 space-y-1">
                <div className="text-xs font-semibold text-slate-100 flex items-center justify-between">
                  <span>{user.display_name}</span>
                  <span
                    className={`px-1.5 py-0.2 rounded text-[10px] font-mono font-bold uppercase border ${getRoleBadgeClass(
                      user.role
                    )}`}
                  >
                    {user.role}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-400 truncate">
                  {user.email}
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400">
                Operating with development headers. Switch to a signed JWT account below to enforce real cryptographic RBAC.
              </p>
            )}
          </div>

          {/* Quick Demo Switcher */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1">
              <Shield className="w-3 h-3 text-cyan-400" />
              <span>One-Click Demo Accounts</span>
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              {DEMO_ACCOUNTS.map((acc) => {
                const isActive = user?.email.toLowerCase() === acc.email.toLowerCase();
                return (
                  <button
                    key={acc.email}
                    type="button"
                    disabled={isLoading}
                    onClick={() => handleDemoSwitch(acc.email)}
                    className={`text-left p-2 rounded-lg border text-xs transition-all ${
                      isActive
                        ? 'bg-cyan-950/50 border-cyan-500/60 ring-1 ring-cyan-500/30'
                        : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-0.5">
                      <span className="font-semibold text-slate-200 truncate text-[11px]">
                        {acc.name.split(' ')[0]}
                      </span>
                      <span
                        className={`px-1 py-0.1 text-[9px] font-mono font-bold uppercase rounded border ${acc.badge}`}
                      >
                        {acc.role}
                      </span>
                    </div>
                    <div className="text-[10px] font-mono text-slate-400 truncate">
                      {acc.email.split('@')[0]}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Manual Login Form */}
          <form onSubmit={handleManualLogin} className="space-y-2 pt-2 border-t border-slate-800">
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1">
              <KeyRound className="w-3 h-3 text-slate-400" />
              <span>Sign In with Credentials</span>
            </div>

            <input
              type="email"
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              placeholder="user@sentinel.local"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-cyan-500 font-mono"
            />

            <input
              type="password"
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
              placeholder="Password..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-cyan-500 font-mono"
            />

            {errorMsg && (
              <div className="p-2 rounded bg-rose-950/40 border border-rose-500/50 text-[11px] font-mono text-rose-300 flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading || !emailInput || !passwordInput}
              className="w-full py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-xs font-semibold text-white transition-colors"
            >
              {isLoading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          {/* Sign Out Button */}
          {user && (
            <div className="pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={handleSignOut}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-slate-950 hover:bg-rose-950/40 border border-slate-800 hover:border-rose-500/40 text-xs text-slate-300 hover:text-rose-300 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5 text-rose-400" />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

