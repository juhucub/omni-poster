// src/hooks/useAuthGuard.ts
import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext.tsx';
import { Loader2 } from 'lucide-react';

export function useAuthGuard(): void {
  const { isLoading, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (isLoading) {
      // you could return a loader here if you wanted,
      // but hooks can't render—so you'll handle loading in your page.
      return;
    }

    if (!isAuthenticated) {
      // preserve where they were heading
      navigate('/login', { state: { from: location }, replace: true });
    }
  }, [isLoading, isAuthenticated, navigate, location]);
}
