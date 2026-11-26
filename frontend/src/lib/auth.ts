import type { ActorRole, SentinelUser } from '@/types/telemetry';

export type AuthUser = SentinelUser;
export type { SentinelUser };

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
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
    user_id: 'usr_approver',
    email: 'approver@sentinel.local',
    display_name: 'Arjun Mehta',
    role: 'approver',
  },
  {
    user_id: 'usr_admin',
    email: 'admin@sentinel.local',
    display_name: 'Priya Nair',
    role: 'admin',
  },
  {
    user_id: 'usr_operator',
    email: 'operator@sentinel.local',
    display_name: 'Devika Rao',
    role: 'operator',
  },
  {
    user_id: 'usr_viewer',
    email: 'viewer@sentinel.local',
    display_name: 'Rohan Das',
    role: 'viewer',
  },
];

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

let cachedUserRaw: string | null = null;
let cachedUserObj: AuthUser | null = null;

function normalizeAuthUser(rawUser: Partial<AuthUser>): AuthUser {
  return {
    user_id: rawUser.user_id || '',
    email: rawUser.email || '',
    display_name: rawUser.display_name || '',
    role: rawUser.role || 'viewer',
    allowed_teams: Array.isArray(rawUser.allowed_teams)
      ? rawUser.allowed_teams
      : ['*'],
    is_demo: Boolean(rawUser.is_demo),
  };
}

export function subscribeAuth(callback: () => void): () => void {
  window.addEventListener(AUTH_CHANGED_EVENT, callback);
  window.addEventListener('storage', callback);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, callback);
    window.removeEventListener('storage', callback);
  };
}

export function getAuthTokenSnapshot(): string | null {
  return getStoredToken();
}

export function getAuthUserSnapshot(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY) ?? '__empty__';
    if (raw !== cachedUserRaw) {
      cachedUserRaw = raw;
      cachedUserObj =
        raw === '__empty__'
          ? null
          : normalizeAuthUser(JSON.parse(raw) as Partial<AuthUser>);
    }
    return cachedUserObj;
  } catch {
    return null;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return normalizeAuthUser(JSON.parse(raw) as Partial<AuthUser>);
  } catch {
    return null;
  }
}

export function setAuthSession(token: string, user: Partial<AuthUser>): void {
  if (typeof window === 'undefined') return;
  try {
    const normalized = normalizeAuthUser(user);
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(normalized));
    cachedUserRaw = null;
    cachedUserObj = null;
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
    cachedUserRaw = null;
    cachedUserObj = null;
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  } catch (err) {
    console.error('Failed to clear Sentinel auth session:', err);
  }
}

export const signOutUser = clearAuthSession;

export async function loginWithCredentials(
  email: string,
  password: string,
): Promise<{ access_token: string; user: AuthUser }> {
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
      const errJson = (await res.json()) as { detail?: string };
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  const data = (await res.json()) as LoginResponse;
  const user = normalizeAuthUser(data.user);
  setAuthSession(data.access_token, user);
  return {
    access_token: data.access_token,
    user,
  };
}
