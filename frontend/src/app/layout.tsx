import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';
import { ApprovalProvider } from '@/components/governance/ApprovalContext';
import { ApprovalModal } from '@/components/governance/ApprovalModal';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'SentinelX - AI Agent Observability & Control Tower',
  description: 'Real-time AI agent fleet monitoring, lineage tracing, and cost attribution.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full dark`}
    >
      <body className="h-full bg-slate-950 text-slate-100 flex overflow-hidden antialiased font-sans">
        <ApprovalProvider>
          <Suspense fallback={<aside className="w-64 border-r border-slate-800 bg-slate-900/70 shrink-0" />}>
            <Sidebar />
          </Suspense>
          <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
            {/* Top header bar renders <LaunchScenarioModal />, <LiveConnectionBadge />, and <UserSessionMenu /> */}
            <Suspense fallback={<header className="relative z-40 h-16 border-b border-slate-800 bg-slate-900/40 shrink-0" />}>
              <Header />
            </Suspense>
            <main className="flex-1 overflow-y-auto bg-slate-950">
              <Suspense fallback={<div className="p-8 text-slate-400 font-mono text-sm">Loading...</div>}>
                {children}
              </Suspense>
            </main>
          </div>
          <ApprovalModal />
        </ApprovalProvider>
      </body>
    </html>
  );
}
