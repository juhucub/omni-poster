import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import CommandRoomPage from './components/command-room/CommandRoom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { useAuth } from './context/AuthContext';
import AccountManager from './pages/AccountManager';
import AuthPage from './pages/AuthPage';
import CharacterLibraryPage from './pages/CharacterLibraryPage';
import GeneratedMediaPage from './pages/GeneratedMediaPage';
import ProjectEditorPage from './pages/ProjectEditorPage';
import ProjectsPage from './pages/ProjectsPage';
import PublishHistoryPage from './pages/PublishHistoryPage';
import VoiceLabPage from './pages/VoiceLabPage';


const AppRoutes: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <AuthPage />} />
      <Route path="/" element={<CommandRoomPage />} />
      <Route
        path="/projects"
        element={
          <ProtectedRoute>
            <ProjectsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId"
        element={
          <ProtectedRoute>
            <ProjectEditorPage />
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
      <Route
        path="/characters"
        element={
          <ProtectedRoute>
            <CharacterLibraryPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/generated-media"
        element={
          <ProtectedRoute>
            <GeneratedMediaPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/history"
        element={
          <ProtectedRoute>
            <PublishHistoryPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/voice-lab"
        element={
          <ProtectedRoute>
            <VoiceLabPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

const App: React.FC = () => (
  <BrowserRouter>
    <AppRoutes />
  </BrowserRouter>
);

export default App;
