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
    <div className="flex min-h-full flex-1 flex-col justify-center px-6 py-12 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-sm">
        <img
          alt = "OmniPoster"
          src='/yeah.jpg'
          className='mx-auto h-10 w-auto'
        />
        <h2 className="mt-10 text-center text-2xl/9 font-bold tracking-tight text-gray-900">
          {mode === 'login' ? 'Sign in to your Account' : 'Create your Account'}
        </h2>
      </div>

      <div className="mt-10 sm:mx-auto sm:w-full sm:max-w-sm">
        <form onSubmit={handleSubmit} className="space-y-6" noValidate>

          <div>
            <label htmlFor="username" className="block text-sm/6 font-medium text-gray-900">
              Username
            </label>
            <div className="mt-2">
              <input
              id="username"
              name="username"
              type="text"
              required
              autoComplete='username'
              value={username}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
              className="block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus: outline-indigo-600 sm:text-sm/6"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="block text-sm/6 font-medium text-gray-900">
                Password
              </label>
              <div className = "text-sm">
                <a href="#" className="font-semibold text-indigo-600 hover:text-indigo-500">
                  { /* Forgot password? */ }
                </a>
            </div>
          </div>
          <div className='mt-2'>
          <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete='current-password'
              value={password}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
              className="block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus: outline-indigo-600 sm:text-sm/6"
              />
          </div>
        </div>

        {mode === 'signup' && (
            <div>
              <label htmlFor="confirm-password" className="block text-sm/6 font-medium text-gray-900">
                Confirm Password
              </label>
              <div className="mt-2">
                <input
                  id="confirm-password"
                  name="confirm-password"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
                  className="block w-full rounded-md bg-white px-3 py-1.5 text-base text-gray-900 outline-1 -outline-offset-1 outline-gray-300 placeholder:text-gray-400 focus:outline-2 focus:-outline-offset-2 focus:outline-indigo-600 sm:text-sm/6"
                />
              </div>
            </div>
          )}

        {info && <div className="text-green-600 text-sm text-center">{info}</div>}
        {error && ( <div className="text-sm text-red-600">{error}</div> )}
      
          <div>
            <button
              type="submit"
              disabled={loading}
              className="flex w-full justify-center rounded-md bg-indigo-600 px-3 py-1.5 text-sm/6 font-semibold text-white shadow-xs hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
              >
                {loading ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </form>

        <p className="mt-10 text-center text-sm/6 text-gray-500">
        {mode === 'login' ? (
          <>
            Not a member?{' '}
            <button onClick={toggleMode} className="font-semibold leading-6 text-indigo-600 hover:text-indigo-500">
                Sign up
            </button>
          </>
        ) : (
          <>
            Already have an account?{' '}
            <button onClick={toggleMode} className="font-semibold leading-6 text-indigo-600 hover:text-indigo-500">
                Sign in
            </button>
          </>
        )}
        </p>
      </div>
    </div>
  )
}

export default AuthPage;