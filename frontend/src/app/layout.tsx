import type { Metadata } from 'next';
import './globals.css';
import { AppShell } from '@/components/AppShell';
import { ASSETS } from '@/lib/assets';

export const metadata: Metadata = {
  title: 'Sentinel-X Control Tower',
  description:
    'Framework-neutral observability, lineage tracing, and runtime governance control tower for multi-agent AI systems.',
  icons: {
    icon: ASSETS.logoLight,
  },
  openGraph: {
    title: 'Sentinel-X Control Tower',
    description:
      'Framework-neutral observability, lineage tracing, and runtime governance control tower for multi-agent AI systems.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Sentinel-X Control Tower',
    description:
      'Framework-neutral observability, lineage tracing, and runtime governance control tower for multi-agent AI systems.',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className="bg-[#F5F9FF] text-[#061838] dark:bg-[#030A17] dark:text-slate-100 transition-colors duration-150"
      >
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
