import React, { useState } from 'react';
import { Navigate } from 'react-router-dom';

import { useAuth } from '../context/AuthContext';

const AuthPage: React.FC = () => {
  const { isAuthenticated, login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuthenticated) {
    return <Navigate to="/projects" replace />;
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      if (mode === 'login') {
        await login({ username, password });
      } else {
        await register({ username, password });
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#08111f] px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-md rounded-3xl border border-white/10 bg-white/[0.04] p-6">
        <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Omni-poster</div>
        <h1 className="mt-2 text-4xl font-semibold">{mode === 'login' ? 'Welcome back' : 'Create account'}</h1>
        <p className="mt-3 text-sm text-slate-400">Sign in to manage projects, voice presets, renders, and publishing workflows.</p>

        <form className="mt-6 space-y-4" onSubmit={submit}>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="Username"
            autoComplete="username"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
          />
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
          />
          {error ? <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
          >
            {busy ? 'Working...' : mode === 'login' ? 'Log In' : 'Create Account'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => setMode((current) => (current === 'login' ? 'register' : 'login'))}
          className="mt-4 text-sm text-cyan-200"
        >
          {mode === 'login' ? 'Need an account? Register' : 'Already have an account? Log in'}
        </button>
      </div>
    </div>
  );
};

export default AuthPage;
