import React from 'react'
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2 } from 'lucide-react';


export function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { isLoading, isAuthenticated } = useAuth();
  const loc = useLocation();

  if (isLoading) return <Loader2 />;
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: loc }} replace />;
  }
  return children;
}
