// src/App.tsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext.tsx';
import  UploadHistory          from './components/media-uploader/UploadHistory.tsx';
import LandingPage             from './pages/LandingPage.tsx';
import AuthPage                from './pages/AuthPage.tsx';
import Dashboard               from './pages/Dashboard.tsx';
import MediaUploader           from './pages/MediaUploader.tsx';
import AccountManager          from './pages/AccountManager.tsx';
import { ProtectedRoute }      from './components/ProtectedRoute.tsx';
import './output.css';
import VideoGenerationPage from './pages/VideoGeneration.tsx';

const AppRoutes: React.FC = () => {
  const { isAuthenticated, isLoading, logout } = useAuth();

  return (
    <>
      {isAuthenticated && (
        <header className="flex justify-end p-4 bg-white shadow">
          <button
            onClick={logout}
            className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Logout
          </button>
        </header>
      )}

      <main className="p-6">
        <Routes>
          {/* Public */}
          <Route path="/home" element={<LandingPage />} />
          <Route
            path="/login"
            element={
              isAuthenticated
                ? <Navigate to="/dashboard" replace />
                : <AuthPage />
            }
          />

          {/* Protected */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/upload"
            element={
              <ProtectedRoute>
                <MediaUploader onUploadSuccess={pid => console.log('Uploaded', pid)} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounts"
            element={
              <ProtectedRoute>
                <AccountManager />
              </ProtectedRoute>
            }
          />
            {/* vid gen */}
            <Route
            path="/vid-gen"
            element={
              <ProtectedRoute>
                <VideoGenerationPage />
              </ProtectedRoute>
            }
          />

          {/* Fallbacks */}
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
    </>
  );
};

const App: React.FC = () => (
  <AuthProvider>
    <UploadHistory>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </UploadHistory>
  </AuthProvider>
);

export default App;
