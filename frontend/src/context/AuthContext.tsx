import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

import apiClient from '../api/client';
import type { AuthResponse, MeResponse } from '../api/models';

type LoginPayload = {
  username: string;
  password: string;
};

type AuthContextValue = {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: MeResponse | null;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshSession = async () => {
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
    void refreshSession();
  }, []);

  const login = async ({ username, password }: LoginPayload) => {
    await apiClient.post<AuthResponse>('/auth/login', { username, password });
    await refreshSession();
  };

  const register = async ({ username, password }: LoginPayload) => {
    await apiClient.post<AuthResponse>('/auth/register', { username, password });
    await refreshSession();
  };

  const logout = async () => {
    await apiClient.post('/auth/logout');
    setUser(null);
  };

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: Boolean(user),
      isLoading,
      user,
      login,
      register,
      logout,
      refreshSession,
    }),
    [isLoading, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider.');
  }
  return context;
};
