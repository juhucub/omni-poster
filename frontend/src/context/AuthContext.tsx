import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

import apiClient from '../api/client';
import type { AuthResponse, MeResponse } from '../api/models';

interface AuthContextType {
  user: MeResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  login: async () => undefined,
  register: async () => undefined,
  logout: async () => undefined,
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadCurrentUser = async () => {
    try {
      const response = await apiClient.get<MeResponse>('/auth/me');
      setUser(response.data);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCurrentUser();
  }, []);

  useEffect(() => {
    const handleExpired = () => setUser(null);
    window.addEventListener('omni-auth-expired', handleExpired);
    return () => window.removeEventListener('omni-auth-expired', handleExpired);
  }, []);

  const login = async (username: string, password: string) => {
    await apiClient.post<AuthResponse>('/auth/login', { username, password });
    await loadCurrentUser();
  };

  const register = async (username: string, password: string) => {
    await apiClient.post<AuthResponse>('/auth/register', { username, password });
    await loadCurrentUser();
  };

  const logout = async () => {
    setUser(null);
    try {
      await apiClient.post('/auth/logout');
    } catch {
      // noop: local state is already cleared
    }
  };

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isLoading,
      login,
      register,
      logout,
    }),
    [user, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => useContext(AuthContext);
