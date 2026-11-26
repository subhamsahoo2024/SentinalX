'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { AlertCircle, KeyRound, Play, ShieldCheck } from 'lucide-react';
import {
  bootstrapAdmin,
  fetchSystemConfig,
  loginDemoSandbox,
} from '@/lib/api';
import { ASSETS } from '@/lib/assets';
import { loginWithCredentials } from '@/lib/auth';
import type { SystemConfigDTO } from '@/types/telemetry';

export default function LoginPage() {
  const router = useRouter();
  const [config, setConfig] = useState<SystemConfigDTO | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadConfig = async () => {
    setLoadingConfig(true);
    setConfigError(null);
    try {
      const data = await fetchSystemConfig();
      setConfig(data);
    } catch (err: unknown) {
      setConfigError(
        err instanceof Error ? err.message : 'Unable to reach Sentinel-X backend',
      );
      setConfig({
        demo_sandbox_enabled: false,
        needs_bootstrap: false,
      });
    } finally {
      setLoadingConfig(false);
    }
  };

  useEffect(() => {
    let active = true;
    fetchSystemConfig()
      .then((data) => {
        if (!active) return;
        setConfig(data);
        setConfigError(null);
        setLoadingConfig(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setConfigError(
          err instanceof Error
            ? err.message
            : 'Unable to reach Sentinel-X backend',
        );
        setConfig({
          demo_sandbox_enabled: false,
          needs_bootstrap: false,
        });
        setLoadingConfig(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleBootstrapSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || demoLoading) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await bootstrapAdmin({
        display_name: displayName,
        email,
        password,
      });
      router.replace('/');
    } catch (err: unknown) {
      setFormError(
        err instanceof Error ? err.message : 'Failed to initialize admin account',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || demoLoading) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await loginWithCredentials(email, password);
      router.replace('/');
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Invalid credentials');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDemoLaunch = async () => {
    if (submitting || demoLoading) return;
    setDemoLoading(true);
    setFormError(null);
    try {
      await loginDemoSandbox();
      router.replace('/');
    } catch (err: unknown) {
      setFormError(
        err instanceof Error ? err.message : 'Failed to launch demo sandbox',
      );
    } finally {
      setDemoLoading(false);
    }
  };

  const needsBootstrap = config?.needs_bootstrap === true;
  const demoSandboxEnabled = config?.demo_sandbox_enabled === true;

  return (
    <div className="fixed inset-0 z-40 overflow-y-auto bg-[#030A17] text-slate-100 flex items-center justify-center px-4 py-12">
      <div className="bg-slate-900 border border-slate-800 max-w-md w-full rounded-xl shadow-2xl p-6 sm:p-8">
        <div className="flex items-center gap-3 pb-6 border-b border-slate-800">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#030A17] border border-slate-800 p-1.5 shrink-0">
            <Image
              src={ASSETS.logoDark}
              alt="Sentinel-X logo"
              width={28}
              height={28}
              referrerPolicy="no-referrer"
              className="h-7 w-7 object-contain"
            />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight text-white">
              SENTINEL-X
            </p>
            <p className="text-xs text-[#7DD3FC]">
              AI Runtime Governance Control Tower
            </p>
          </div>
        </div>

        {configError && (
          <div className="mt-5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" aria-hidden="true" />
            <div className="flex-1">
              <p className="font-medium">{configError}</p>
              <button
                type="button"
                onClick={() => void loadConfig()}
                className="mt-1 underline text-amber-300 hover:text-white"
              >
                Retry connection
              </button>
            </div>
          </div>
        )}

        {loadingConfig ? (
          <div className="py-10 text-center space-y-3">
            <div className="mx-auto h-6 w-6 rounded-full border-2 border-[#00C2FF] border-t-transparent animate-spin" />
            <p className="text-xs text-slate-400">
              Checking organization configuration...
            </p>
          </div>
        ) : needsBootstrap ? (
          <form onSubmit={handleBootstrapSubmit} className="mt-6 space-y-4">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full border border-[#00C2FF]/30 bg-[#0257D5]/20 px-2.5 py-0.5 text-[11px] font-medium text-[#7DD3FC] mb-2">
                <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                <span>First-Time Setup</span>
              </div>
              <h1 className="text-lg font-semibold text-white">
                Initialize Organization Admin
              </h1>
              <p className="text-xs text-slate-400 mt-1">
                Create the primary administrator account for your Sentinel-X control tower.
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label
                  htmlFor="bootstrap-name"
                  className="block text-xs font-medium text-slate-300 mb-1"
                >
                  Full Name
                </label>
                <input
                  id="bootstrap-name"
                  type="text"
                  required
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Priya Nair"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="bootstrap-email"
                  className="block text-xs font-medium text-slate-300 mb-1"
                >
                  Administrator Email
                </label>
                <input
                  id="bootstrap-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@company.com"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="bootstrap-password"
                  className="block text-xs font-medium text-slate-300 mb-1"
                >
                  Password
                </label>
                <input
                  id="bootstrap-password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Choose a strong password"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-[#00C2FF] focus:outline-none"
                />
              </div>
            </div>

            {formError && (
              <div className="rounded-lg border border-red-500/40 bg-red-950/60 px-3 py-2 text-xs text-red-200">
                {formError}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || demoLoading}
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-[#0257D5] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#0346B0] disabled:opacity-50 transition-colors"
            >
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              <span>
                {submitting ? 'Initializing...' : 'Initialize Organization Admin'}
              </span>
            </button>
          </form>
        ) : (
          <form onSubmit={handleLoginSubmit} className="mt-6 space-y-4">
            <div>
              <h1 className="text-lg font-semibold text-white">
                Sign In to SENTINEL-X
              </h1>
              <p className="text-xs text-slate-400 mt-1">
                Authenticate with your organization credentials to access telemetry and governance.
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label
                  htmlFor="login-email"
                  className="block text-xs font-medium text-slate-300 mb-1"
                >
                  Email
                </label>
                <input
                  id="login-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="login-password"
                  className="block text-xs font-medium text-slate-300 mb-1"
                >
                  Password
                </label>
                <input
                  id="login-password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-[#00C2FF] focus:outline-none"
                />
              </div>
            </div>

            {formError && (
              <div className="rounded-lg border border-red-500/40 bg-red-950/60 px-3 py-2 text-xs text-red-200">
                {formError}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || demoLoading}
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-[#0257D5] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#0346B0] disabled:opacity-50 transition-colors"
            >
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              <span>{submitting ? 'Signing In...' : 'Sign In'}</span>
            </button>
          </form>
        )}

        {!loadingConfig && demoSandboxEnabled && (
          <div className="mt-6">
            <div className="relative flex items-center py-2">
              <div className="flex-grow border-t border-slate-800" />
              <span className="mx-3 shrink text-[11px] uppercase tracking-wider text-slate-500">
                or explore in sandbox mode
              </span>
              <div className="flex-grow border-t border-slate-800" />
            </div>

            <button
              type="button"
              disabled={submitting || demoLoading}
              onClick={() => void handleDemoLaunch()}
              className="mt-3 w-full inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-slate-800 hover:border-slate-600 disabled:opacity-50 transition-colors"
            >
              <Play className="h-4 w-4 text-amber-400" aria-hidden="true" />
              <span>
                {demoLoading
                  ? 'Launching Demo Sandbox...'
                  : 'Launch Interactive Demo'}
              </span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

