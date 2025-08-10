import React, { useState, ChangeEvent, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext.tsx';

const LoginForm: React.FC<{
  onSuccess?: () => void;
  setError: (msg: string | null) => void;
  setLoading: (loading: boolean) => void;
}> = ({ onSuccess, setError, setLoading }) => {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    if (!username.trim() || !password) {
      setError('Username and password are required.');
      setLoading(false);
      return;
    }

    try {
      await login(username.trim(), password);
      onSuccess?.();
    } catch (err: any) {
      const serverMsg = err.response?.data?.detail;
      setError(serverMsg ?? 'A login error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  }
  

  return  (
    <form onSubmit={submit} className="space-y-6" autoComplete='on'>
      <div>
        <label htmlFor="login-username" className="block text-sm/6 font-medium text-gray-900">
          Username
        </label>
        <input
          id="login-username"
          name="username"
          type="text"
          autoComplete="username"
          required
          value={username}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
          autoCapitalize='none'
          spellCheck='false'
          className="mt-2 block w-full rounded-md border-gray-300 px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus:outline-indigo-600 sm:text-sm/6"
        />
      </div>

      <div>
        <div className="flex items-center justify-between">
          <label htmlFor="login-password" className="block text-sm/6 font-medium text-gray-900">
            Password
          </label>
        </div>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
          className="mt-2 block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus:outline-indigo-600 sm:text-sm/6"
        />
      </div>

      <button
        type="submit"
        className="flex w-full justify-center rounded-md bg-indigo-600 px-3 py-1.5 text-sm/6 font-semibold text-white shadow-xs hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
      >
        Sign in
      </button>
    </form>
  );
};

const SignupForm: React.FC<{
  onSuccess?: () => void;
  setError: (msg: string | null) => void;
  setLoading: (v: boolean) => void;
  setInfo: (msg: string | null) => void;
}> = ({ onSuccess, setError, setLoading, setInfo }) => {
  const { register } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);

    const u = username.trim();
    if (!u || !password) {
      setError('Username and password are required.');
      setLoading(false);
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      setLoading(false);
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      setLoading(false);
      return;
    }

    try {
      await register(u, password);
      setInfo('Account created & logged in!');
      onSuccess?.();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Sign up failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-6" autoComplete="on">
      <div>
        <label htmlFor="signup-username" className="block text-sm/6 font-medium text-gray-900">
          Username
        </label>
        <input
          id="signup-username"
          name="username"
          type="text"
          autoComplete="username"
          required
          value={username}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
          autoCapitalize="none"
          spellCheck={false}
          className="mt-2 block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus:outline-indigo-600 sm:text-sm/6"
        />
      </div>

      <div>
        <label htmlFor="signup-password" className="block text-sm/6 font-medium text-gray-900">
          Password
        </label>
        <input
          id="signup-password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
          className="mt-2 block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus:outline-indigo-600 sm:text-sm/6"
        />
      </div>

      <div>
        <label htmlFor="signup-confirm" className="block text-sm/6 font-medium text-gray-900">
          Confirm Password
        </label>
        <input
          id="signup-confirm"
          name="confirm-password"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
          className="mt-2 block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus:outline-indigo-600 sm:text-sm/6"
        />
      </div>

      <button
        type="submit"
        className="flex w-full justify-center rounded-md bg-indigo-600 px-3 py-1.5 text-sm/6 font-semibold text-white shadow-xs hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
      >
        Create account
      </button>
    </form>
  );
};

const AuthPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  if (isAuthenticated) return null;

  const afterSuccess = () => {
    // navigate + unmount form (password‑manager friendly)
    nav('/dashboard', { replace: true });
  };

  return (
    <div className="flex min-h-full flex-1 flex-col justify-center px-6 py-12 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-sm">
        <img alt="OmniPoster" src="/yeah.jpg" className="mx-auto h-10 w-auto" />
        <h2 className="mt-10 text-center text-2xl/9 font-bold tracking-tight text-gray-900">
          {mode === 'login' ? 'Sign in to your Account' : 'Create your Account'}
        </h2>
      </div>

      <div className="mt-10 sm:mx-auto sm:w-full sm:max-w-sm">
        {mode === 'login' ? (
          <LoginForm onSuccess={afterSuccess} setError={setError} setLoading={setLoading} />
        ) : (
          <SignupForm onSuccess={afterSuccess} setError={setError} setLoading={setLoading} setInfo={setInfo} />
        )}

        {info && (
          <div className="mt-3 text-center text-sm text-green-600" role="status" aria-live="polite">
            {info}
          </div>
        )}
        {error && (
          <div className="mt-3 text-sm text-red-600" role="alert" aria-live="assertive">
            {error}
          </div>
        )}

        <p className="mt-10 text-center text-sm/6 text-gray-500">
          {mode === 'login' ? (
            <>
              Not a member?{' '}
              <button
                onClick={() => { setMode('signup'); setError(null); setInfo(null); }}
                className="font-semibold leading-6 text-indigo-600 hover:text-indigo-500"
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <button
                onClick={() => { setMode('login'); setError(null); setInfo(null); }}
                className="font-semibold leading-6 text-indigo-600 hover:text-indigo-500"
              >
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  );
};

export default AuthPage;