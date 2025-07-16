import React, { createContext, useContext, useState, useEffect, ReactNode, useMemo } from 'react';
import axios, { AxiosInstance } from 'axios';

// Define shape of auth context
interface AuthContextType {
  isAuthenticated: boolean;
  accessToken: string | null;
  user: Record<string, any> | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

// Default values
export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  accessToken: null,
  user: null,
  login: async () => {},
  register: async () => {},
  logout: () => {},
  refreshToken: async () => {},
});

interface AuthProviderProps {
  children: ReactNode;
  apiClient?: AxiosInstance; // allow custom axios instance
}

/**
 * AuthProvider wraps the app and provides authentication context.
 * - Stores JWT access token securely in memory/localStorage.
 * - Sets up axios interceptors to attach token to requests.
 * - Handles login, logout, and token refresh flows.
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children, apiClient }) => {
  const [accessToken, setAccessToken] = useState<string | null>(() => {
    // Initialize from localStorage if available
    return localStorage.getItem('access_token');
  });
  const [user, setUser] = useState<Record<string, any> | null>(null);

  // Determine auth status
  const isAuthenticated = Boolean(accessToken);

   // memoize client so interceptors don't get re-registered on every render
   const client = useMemo<AxiosInstance>(
    () =>
      axios.create({
        baseURL:
          process.env.REACT_APP_API_URL || "http://127.0.0.1:8000",
        withCredentials: true,
      }),
    []
  );

  // Attach interceptor to include Authorization header
  useEffect(() => {
    const requestInterceptor = client.interceptors.request.use((config) => {
      if (accessToken && config.headers) {
        config.headers['Authorization'] = `Bearer ${accessToken}`;
      }
      return config;
    });
    return () => {
      client.interceptors.request.eject(requestInterceptor);
    };
  }, [accessToken, client]);

  // On mount, optionally fetch current user profile
  useEffect(() => {
    if (!accessToken) {
      setUser(null);
      return;
    }
      client
        .get('/auth/me')
        .then(res => setUser(res.data))
        .catch(() => {
          // Token invalid or expired
          setAccessToken(null);
          localStorage.removeItem('access_token');
        });
    }, [accessToken, client]);

  /**
   * Authenticate user and store token.
   */
  const login = async (username: string, password: string) => {
    try {
      const response = await client.post('/auth/login', { username, password });
      const token = response.data.access_token;
      // Persist token in memory and localStorage
      setAccessToken(token);
      localStorage.setItem('access_token', token);
      // Fetch user profile
      const profile = await client.get('/auth/me');
      setUser(profile.data);
    } catch (error) {
      // Propagate error for UI handling
      throw error;
    }
  };

  const register = async (username: string, password: string) => {
    // calls FastAPI /auth/register (cookie + token)
    const resp = await client.post<TokenResponse>('/auth/register', { username, password });
    const token = resp.data.access_token;
    setAccessToken(token);
    localStorage.setItem('access_token', token);
    // now fetch profile
    const profile = await client.get<MeResponse>('/auth/me');
    setUser({ id: profile.data.id, username: profile.data.username });
  };

  /**
   * Clear authentication state.
   */
  const logout = () => {
    setAccessToken(null);
    setUser(null);
    localStorage.removeItem('access_token');
    // Optionally notify backend
    client.post('/auth/logout').catch(() => {});
  };

  /**
   * Refresh JWT access token using a refresh token cookie.
   */
  const refreshToken = async () => {
    try {
      const response = await client.post('/auth/refresh', {}, { withCredentials: true });
      const token = response.data.accessToken as string;
      setAccessToken(token);
      localStorage.setItem('access_token', token);
    } catch (error) {
      logout();
    }
  };

  // Optionally auto-refresh token before expiry
  useEffect(() => {
    if (!accessToken) return;
    // Decode token to get expiry (exp) and schedule refresh a bit early
    try {
      const [, payload] = accessToken.split('.');
      const { exp } = JSON.parse(atob(payload));
      const expiresAt = exp * 1000;
      const now = Date.now();
      const timeout = expiresAt - now - 60 * 1000; // 1 min before expiry
      if (timeout > 0) {
        const timer = setTimeout(() => refreshToken(), timeout);
        return () => clearTimeout(timer);
      }
    } catch {
      // Invalid token format; require re-login
      logout();
    }
  }, [accessToken]);

  return (
    <AuthContext.Provider value={{
      isAuthenticated, accessToken, user,
      login, register,   // ← here
      logout, refreshToken
    }}>
      {children}
    </AuthContext.Provider>
  );
};

/**
 * Custom hook to consume auth context.
 */
export const useAuth = () => useContext(AuthContext)
