import React from 'react';
import {BrowserRouter, Routes, Route, Navigate} from 'react-router-dom';
import { useAuth }     from './context/AuthContext.tsx';
import MediaUploader   from './pages/MediaUploader.tsx';
import AuthPage from './pages/AuthPage.tsx';
import Dashboard from './pages/Dashboard.tsx';
import AccountManager from './pages/AccountManager.tsx';

const App: React.FC = () => {
  const { isAuthenticated, logout } = useAuth();

  return (
    <BrowserRouter>
      {/* Show logout button whenever the user is logged in */}
      {isAuthenticated && (
        <header className="flex justify-end p-4 bg-white shadow relative z-0">
          <button
            onClick={() => logout()}
            className="relative z-200 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Logout
          </button>
        </header>
      )}

      <main className="p-6">
        <Routes>
          {/* Public route for login/signup */}
          <Route
            path="/login"
            element={
              isAuthenticated
                ? <Navigate to="/dashboard" replace />
                : <AuthPage />
            }
          />

          {/* Protected dashboard */}
          <Route
            path="/dashboard"
            element={
              isAuthenticated
                ? <Dashboard />
                : <Navigate to="/login" replace />
            }
          />

          {/* Protected upload page */}
          <Route
            path="/upload"
            element={
              isAuthenticated
                ? (
                  <MediaUploader
                    onUploadSuccess={(projectId) => {
                      // e.g. redirect to dashboard or store in context
                      console.log("Uploaded, new project id:", projectId);
                    }}
                  />
                )
                : <Navigate to="/login" replace />
            }
          />

          <Route
            path="/accounts"
            element={isAuthenticated
              ? <AccountManager />
              : <Navigate to="/login" replace />
            }
          />


          {/* Redirect root and all unknown routes */}
          <Route
            path="/"
            element={
              isAuthenticated
                ? <Navigate to="/dashboard" replace />
                : <Navigate to="/login" replace />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
};

export default App;
