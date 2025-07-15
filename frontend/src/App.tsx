import React, { useState } from 'react';
import MediaUploader   from './pages/MediaUploader.tsx';
import AuthPage from './pages/AuthPage.tsx';
import { useAuth }     from './context/AuthContext.tsx';

const App: React.FC = () => {
  const { isAuthenticated, login, logout } = useAuth();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<{ title: string; tags: string[]; hashtags: string[] } | null>(null);
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [scheduledTime, setScheduledTime] = useState<string | null>(null);
  const [workflowStep, setWorkflowStep] = useState<'upload'|'preview'|'meta'|'platform'|'schedule'|'done'>('upload');

  // Advance to next step
  const next = () => {
    switch (workflowStep) {
      case 'upload':   return setWorkflowStep('preview');
      case 'preview':  return setWorkflowStep('meta');
      case 'meta':     return setWorkflowStep('platform');
      case 'platform': return setWorkflowStep('schedule');
      case 'schedule': return setWorkflowStep('done');
      default:         return;
    }
  };

  const handleLogout = () => {
    logout();
  }
  /*
  // Final schedule submission
  const handleSubmitAll = async () => {
    if (!projectId || !metadata || platforms.length === 0 || !scheduledTime) return;
    try {
      await fetch('/schedule', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          platforms,
          scheduled_time: scheduledTime
        })
      });
      next(); // moves to 'done'
    } catch (e) {
      console.error(e);
    }
  }; */

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <AuthPage />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
       <header className="flex justify-end mb-6">
        <button onClick={() => {
          logout();
          // if you need to reset any workflow state, do it here
          setProjectId(null);
          //setMetadata(null);
          //setPlatforms([]);
          //setScheduledTime(null);
          setWorkflowStep('upload');
        }}>
          Logout
        </button>
      </header>

      <main className="max-w-4xl mx-auto space-y-8">
        {workflowStep === 'upload' && <MediaUploader onUploadSuccess={id => { setProjectId(id); next(); }} />}

        {workflowStep === 'preview' && projectId && (
          <VideoPreview projectId={projectId} onReady={() => next()} />
        )}

        {workflowStep === 'meta' && projectId && (
          <MetadataForm projectId={projectId} onComplete={data => { setMetadata(data); next(); }} />
        )}

        {workflowStep === 'platform' && (
          <PlatformSelector initialSelected={platforms} onChange={sel => setPlatforms(sel)} />
        )}

        {workflowStep === 'schedule' && (
          <SchedulePicker
            onSchedule={iso => { setScheduledTime(iso); /* keep on this step until submit */ }}
          />
        )}

        {workflowStep === 'schedule' && scheduledTime && (
          <button onClick={handleSubmitAll} className="btn">Schedule Upload</button>
        )}

        {workflowStep === 'done' && (
          <div className="text-green-700">Scheduled! <button onClick={() => window.location.reload()}>Start over</button></div>
        )}

        <section>
          <h2>Upload History</h2>
         
        </section>
      </main>
    </div>
  );
};

export default App;
