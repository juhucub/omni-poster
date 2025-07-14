import React, { useState, ChangeEvent, FormEvent } from 'react';
import { useAuth } from '../context/AuthContext.tsx';

/**
 * AuthPage
 * Provides both Login and Signup flows in one component.
 * Securely handles credentials, displays errors, and integrates with AuthContext.
 */
const AuthPage: React.FC = () => {
  const { login, register, isAuthenticated } = useAuth();
  const [mode, setMode] = useState<'login' | 'signup'>('login');

  // Shared fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  // Toggle between Login and Signup
  const toggleMode = () => {
    setError(null);
    setInfo(null);
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setMode(mode === 'login' ? 'signup' : 'login');
  };

  // Form submission
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);

    // Basic validation
    const trimmedUsername = username.trim();
    if (!trimmedUsername || !password) {
      setError('Username and password are required.');
      setLoading(false);
      return;
    }
    if (mode === 'signup') {
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
    }

    try {
      if (mode === 'login') {
        // Use AuthContext login
        await login(trimmedUsername, password);
      } else {
        // Signup via backend
        
        await register(trimmedUsername, password);
        setInfo('Account created & logged in!');
      }
    } catch (err: any) {
      // Distinguish register vs login errors
      const serverMsg = err.response?.data?.detail;
      if (serverMsg) {
        setError(serverMsg);
      } else {
        setError('An error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // If already authenticated, nothing to show here
  if (isAuthenticated) return null;

  return (
    <div className="max-w-md mx-auto mt-12 p-6 bg-white shadow rounded">
      <h2 className="text-2xl font-semibold mb-4 capitalize">{mode}</h2>
      {info && <div className="mb-2 text-green-600">{info}</div>}
      {error && <div className="mb-4 text-red-600">{error}</div>}
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="username" className="block text-sm font-medium">Username</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
            required
            className="mt-1 block w-full border-gray-300 rounded p-2 focus:ring focus:border-blue-300"
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
            required
            minLength={8}
            className="mt-1 block w-full border-gray-300 rounded p-2 focus:ring focus:border-blue-300"
          />
        </div>

        {mode === 'signup' && (
          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium">Confirm Password</label>
            <input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              className="mt-1 block w-full border-gray-300 rounded p-2 focus:ring focus:border-blue-300"
            />
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? `${mode}…` : mode === 'login' ? 'Log In' : 'Sign Up'}
        </button>
      </form>

      <div className="mt-4 text-center text-sm">
        {mode === 'login' ? (
          <span>
            Don’t have an account?{' '}
            <button onClick={toggleMode} className="underline text-blue-600 hover:text-blue-800">
              Sign Up
            </button>
          </span>
        ) : (
          <span>
            Already have an account?{' '}
            <button onClick={toggleMode} className="underline text-blue-600 hover:text-blue-800">
              Log In
            </button>
          </span>
        )}
      </div>
    </div>
  );
};

export default AuthPage;