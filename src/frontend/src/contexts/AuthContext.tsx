/**
 * AuthContext.tsx — Session state for the entire application.
 *
 * AuthProvider mounts once at the root. On mount it calls GET /api/v1/auth/me
 * to restore a session from the httpOnly cookie. While the check is in flight,
 * status === 'loading' — ProtectedRoute renders a skeleton, never a redirect,
 * so refreshing a gated page keeps the user where they are.
 *
 * Mock mode (VITE_DATA_SOURCE=mock):
 *   The /me call is skipped entirely. Auth resolves immediately to the demo
 *   user so judges can browse the full app with no backend. The DataModeIndicator
 *   in AppLayout labels this clearly.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
  isDemo: boolean;
}

export type AuthStatus = 'loading' | 'authed' | 'anon';

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Called by the API adapter on any 401 to clear session once. */
  clearSession: () => void;
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const IS_MOCK = (import.meta.env.VITE_DATA_SOURCE ?? 'mock') === 'mock';
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api') + '/v1';

const MOCK_USER: AuthUser = {
  id: 'mock-user',
  email: 'demo@coldfront.app',
  fullName: 'Demo Operator',
  isDemo: true,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail ?? detail;
    } catch {
      // ignore
    }
    const err = new Error(detail) as Error & { status: number };
    err.status = res.status;
    throw err;
  }
  // 204 No Content — return empty object
  if (res.status === 204) return {} as T;
  return res.json() as Promise<T>;
}

function mapUser(raw: Record<string, unknown>): AuthUser {
  return {
    id: raw.id as string,
    email: raw.email as string,
    fullName: (raw.fullName ?? raw.full_name) as string,
    isDemo: (raw.isDemo ?? raw.is_demo) as boolean,
  };
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  // Guard against multiple 401-redirect loops
  const redirectingRef = useRef(false);

  // Restore session on mount
  useEffect(() => {
    if (IS_MOCK) {
      // Mock mode: skip /me, resolve as demo user immediately
      setUser(MOCK_USER);
      setStatus('authed');
      return;
    }

    fetch(`${API_BASE}/auth/me`, { credentials: 'include' })
      .then((res) => {
        if (res.ok) return res.json();
        return null;
      })
      .then((data) => {
        if (data) {
          setUser(mapUser(data));
          setStatus('authed');
        } else {
          setUser(null);
          setStatus('anon');
        }
      })
      .catch(() => {
        setUser(null);
        setStatus('anon');
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    if (IS_MOCK) {
      // Stub: always succeed in mock mode
      setUser(MOCK_USER);
      setStatus('authed');
      return;
    }
    const data = await apiPost<Record<string, unknown>>('/auth/login', { email, password });
    setUser(mapUser(data));
    setStatus('authed');
    redirectingRef.current = false;
  }, []);

  const signup = useCallback(async (email: string, password: string, fullName: string) => {
    if (IS_MOCK) {
      setUser({ ...MOCK_USER, email, fullName, isDemo: false });
      setStatus('authed');
      return;
    }
    const data = await apiPost<Record<string, unknown>>('/auth/signup', {
      email,
      password,
      full_name: fullName,
    });
    setUser(mapUser(data));
    setStatus('authed');
    redirectingRef.current = false;
  }, []);

  const logout = useCallback(async () => {
    if (!IS_MOCK) {
      await apiPost('/auth/logout', {}).catch(() => {});
    }
    setUser(null);
    setStatus('anon');
  }, []);

  const clearSession = useCallback(() => {
    if (redirectingRef.current) return;
    redirectingRef.current = true;
    setUser(null);
    setStatus('anon');
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, login, signup, logout, clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}
