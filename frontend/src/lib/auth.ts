import type { ActorRole, SentinelUser } from '@/types/telemetry';

export type { SentinelUser };

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: SentinelUser;
}

export const TOKEN_KEY = 'sentinel_jwt';
export const USER_KEY = 'sentinel_user';
export const AUTH_CHANGED_EVENT = 'sentinel-auth-changed';

export const DEMO_ACCOUNTS: {
  user_id: string;
  email: string;
  display_name: string;
  role: ActorRole;
}[] = [
  {
    user_id: 'usr-approver-01',
    email: 'approver@sentinel.local',
    display_name: 'Arjun Mehta',
    role: 'approver',
  },
  {
    user_id: 'usr-admin-01',
    email: 'admin@sentinel.local',
    display_name: 'Priya Nair',
    role: 'admin',
  },
  {
    user_id: 'usr-operator-01',
    email: 'operator@sentinel.local',
    display_name: 'Devika Rao',
    role: 'operator',
  },
  {
    user_id: 'usr-viewer-01',
    email: 'viewer@sentinel.local',
    display_name: 'Rohan Das',
    role: 'viewer',
  },
];

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser(): SentinelUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SentinelUser;
  } catch {
    return null;
  }
}

export function setAuthSession(token: string, user: SentinelUser): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  } catch (err) {
    console.error('Failed to save Sentinel auth session:', err);
  }
}

export function clearAuthSession(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  } catch (err) {
    console.error('Failed to clear Sentinel auth session:', err);
  }
}

export const signOutUser = clearAuthSession;

export async function loginWithCredentials(
  email: string,
  password: string,
): Promise<{ access_token: string; user: SentinelUser }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email: email.trim().toLowerCase(),
      password,
    }),
  });

  if (!res.ok) {
    let errorDetail = `Login failed (${res.status} ${res.statusText})`;
    try {
      const errJson = await res.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  const data = (await res.json()) as LoginResponse;
  setAuthSession(data.access_token, data.user);
  return {
    access_token: data.access_token,
    user: data.user,
  };
}
