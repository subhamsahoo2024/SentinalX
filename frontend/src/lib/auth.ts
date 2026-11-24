export interface SentinelUser {
  user_id: string;
  email: string;
  display_name: string;
  role: 'admin' | 'approver' | 'operator' | 'viewer' | string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: SentinelUser;
}

const TOKEN_KEY = 'sentinel_jwt';
const USER_KEY = 'sentinel_user';
const AUTH_CHANGED_EVENT = 'sentinel-auth-changed';

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

export async function loginWithCredentials(
  email: string,
  password: string
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

