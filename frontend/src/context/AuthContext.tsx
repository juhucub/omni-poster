import React, { createContext, useContext, useState, useEffect, ReactNode, useMemo, useCallback } from 'react';
import axios, { AxiosInstance } from 'axios';
import type { TokenResponse, MeResponse } from '../api/models'; 

// Define shape of auth context
interface AuthContextType {
  user: MeResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

// Default values
const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  login: async () => {},
  register: async () => {},
  logout: async () => {},
});

/**
 * Centralized Axios instance for auth-protected API calls.
 * - withCredentials: sends HTTP-only cookies for secure sessions.
 * - JSON default headers.
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

 /**
 * Response interceptor to handle unauthorized errors and attempt silent refresh.
 */
apiClient.interceptors.response.use(
  response => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      try {
        // attempt to refresh token (backend must set a new cookie)
        await apiClient.post('/auth/refresh');
        // retry original request
        return apiClient.request(error.config!);
      } catch {
        // refresh failed: proceed to logout
        authLogout();
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Internal logout helper for interceptor (no context access).
 */
let authLogout: () => Promise<void> = async () => {};
 

/**
 * AuthProvider wraps the app, manages the user session entirely in memory and HTTP-only cookies.
 * Avoids localStorage to mitigate XSS risks.
 */
export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  /**
   * Perform initial "whoami" check on mount.
   */
  useEffect(() => {
    apiClient
      .get<MeResponse>('/auth/me')
      .then(res => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  /**
   * Log in via credentials; backend sets HTTP-only cookie and returns token JSON.
   */
  const login = useCallback(async (username: string, password: string) => {
    await apiClient.post<TokenResponse>('/auth/login', { username, password });
    const me = await apiClient.get<MeResponse>('/auth/me');
    setUser(me.data);
  }, []);

  /**
   * Register a new account; backend sets HTTP-only cookie as well.
   */
  const register = useCallback(async (username: string, password: string) => {
    await apiClient.post<RegisterResponse>('/auth/register', { username, password });
    const me = await apiClient.get<MeResponse>('/auth/me');
    setUser(me.data);
  }, []);

  /**
   * Clear session on logout both client- and server-side.
   */
  const logout = useCallback(async () => {
    setUser(null);
    try {
      await apiClient.post('/auth/logout');
    } catch {
      // ignore network errors on logout
    }
  }, []);

  // assign internal logout for interceptor use
  authLogout = logout;

  /**
   * Memoized context value to avoid unnecessary re-renders.
   */
  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isLoading,
      login,
      register,
      logout,
    }),
    [user, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Hook to consume authentication context.
 */
export const useAuth = (): AuthContextType => useContext(AuthContext);
  