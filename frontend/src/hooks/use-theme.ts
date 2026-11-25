'use client';

import { useCallback, useEffect, useSyncExternalStore } from 'react';

export type ThemeMode = 'light' | 'dark';

const THEME_STORAGE_KEY = 'sentinel_x_theme';
const THEME_CHANGE_EVENT = 'sentinel:theme-changed';

function readStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'light';
  try {
    const val = window.localStorage.getItem(THEME_STORAGE_KEY);
    return val === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function subscribeTheme(callback: () => void) {
  window.addEventListener(THEME_CHANGE_EVENT, callback);
  window.addEventListener('storage', callback);
  return () => {
    window.removeEventListener(THEME_CHANGE_EVENT, callback);
    window.removeEventListener('storage', callback);
  };
}

export function applyThemeClass(theme: ThemeMode): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

export function setThemeMode(theme: ThemeMode): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // ignore storage errors
  }
  applyThemeClass(theme);
  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: theme }));
}

export function useTheme() {
  const theme = useSyncExternalStore<ThemeMode>(
    subscribeTheme,
    readStoredTheme,
    () => 'light',
  );

  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeMode(theme === 'dark' ? 'light' : 'dark');
  }, [theme]);

  return { theme, isDark: theme === 'dark', toggleTheme, setTheme: setThemeMode };
}

