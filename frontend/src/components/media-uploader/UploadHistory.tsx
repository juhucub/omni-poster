import React, { FC, useState, useEffect } from 'react';
import API from '../../api/client.ts';
import { useAuth } from '../../context/AuthContext.tsx';

interface UploadRecord {
  project_id: string;
  filename: string;
  url: string;
  content_type: string;
  uploader_id: string;
  uploaded_at: string;
}

interface UploadHistoryProps {
  onSelect: (projectId: string) => void;
  refreshTrigger?: number;
}

const UploadHistory: FC<UploadHistoryProps> = ({ onSelect, refreshTrigger }) => {
  const { logout, isAuthenticated, isLoading: authLoading } = useAuth();
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  const fetchHistory = async (skipAuth = false) => {
    // Don't fetch if not authenticated (unless explicitly skipping auth check)
    if (!skipAuth && !isAuthenticated) {
      console.log('UploadHistory: Not authenticated, skipping fetch');
      setLoading(false);
      return;
    }

    console.log('UploadHistory: Fetching upload history...');
    setLoading(true);
    setError(null);
    
    try {
      const res = await API.get<UploadRecord[]>('/upload_history');
      console.log('UploadHistory: Fetch successful:', res.data.length, 'records');
      setUploads(res.data);
      setRetryCount(0); // Reset retry count on success
    } catch (err: any) {
      console.error('UploadHistory error:', err.response?.status, err.response?.data);
      
      if (err.response?.status === 401) {
        console.warn('UploadHistory: 401 Unauthorized - this might be a backend configuration issue');
        
        // Instead of immediately logging out, let's be more careful
        if (retryCount < 2) {
          console.log('UploadHistory: Retrying fetch in case of transient auth issue...');
          setRetryCount(prev => prev + 1);
          // Retry after a short delay
          setTimeout(() => fetchHistory(true), 1000);
          return;
        } else {
          console.log('UploadHistory: Multiple 401 errors, logging out');
          setError('Authentication failed. You will be redirected to login.');
          // Delay logout slightly to show the error message
          setTimeout(() => logout(), 2000);
          return;
        }
      }
      
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to fetch upload history';
      setError(errorMessage);
      console.error('UploadHistory error details:', errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Wait for auth to be resolved before fetching history
  useEffect(() => {
    console.log('UploadHistory: useEffect triggered', {
      authLoading,
      isAuthenticated,
      refreshTrigger
    });
    
    if (authLoading) {
      console.log('UploadHistory: Auth still loading, waiting...');
      return; // Wait for auth to resolve
    }
    
    if (isAuthenticated) {
      fetchHistory();
    } else {
      console.log('UploadHistory: Not authenticated, not fetching');
      setLoading(false);
    }
  }, [refreshTrigger, isAuthenticated, authLoading]);

  // Show auth loading state
  if (authLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          <span className="ml-2 text-gray-600">Checking authentication…</span>
        </div>
      </div>
    );
  }

  // Show not authenticated state
  if (!isAuthenticated) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
          <div className="flex">
            <span className="text-yellow-400">⚠️</span>
            <div className="ml-3">
              <h4 className="text-sm font-medium text-yellow-800">Authentication Required</h4>
              <p className="text-sm text-yellow-700 mt-1">Please log in to view upload history.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          <span className="ml-2 text-gray-600">
            Loading history… {retryCount > 0 && `(retry ${retryCount})`}
          </span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <span className="text-red-400">⚠️</span>
            <div className="ml-3">
              <h4 className="text-sm font-medium text-red-800">Error loading history</h4>
              <p className="text-sm text-red-700 mt-1">{error}</p>
              {!error.includes('Authentication failed') && (
                <button
                  onClick={() => {
                    setRetryCount(0);
                    fetchHistory();
                  }}
                  className="mt-2 text-sm bg-red-100 hover:bg-red-200 text-red-800 px-3 py-1 rounded border border-red-300"
                >
                  Try Again
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (uploads.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4 text-center py-8 text-gray-500">
        <div className="text-4xl mb-2">📤</div>
        <p>No uploads yet</p>
        <p className="text-sm">Your uploaded files will appear here.</p>
      </div>
    );
  }

  const sorted = [...uploads].sort(
    (a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
  );

  const formatTimestamp = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  const iconFor = (ct: string) =>
    ct.startsWith('video/') ? '🎥' :
    ct.startsWith('audio/') ? '🎵' :
    ct.startsWith('image/') ? '🖼️' : '📄';

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold mb-4">Upload History</h3>
      <div className="space-y-2">
        {sorted.map((u, i) => (
          <div
            key={`${u.project_id}-${u.filename}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(u.project_id)}
            onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onSelect(u.project_id)}
            className={`
              p-3 rounded-md border cursor-pointer transition-colors
              ${i % 2 === 0 ? 'bg-gray-50' : 'bg-white'}
              hover:bg-blue-50 hover:border-blue-200 border-gray-200
            `}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3 flex-1 min-w-0">
                <span className="text-xl">{iconFor(u.content_type)}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{u.filename}</p>
                  <p className="text-xs text-gray-500 truncate">Project: {u.project_id}</p>
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-xs text-gray-500">{formatTimestamp(u.uploaded_at)}</p>
                <p className="text-xs text-gray-400 capitalize">{u.content_type.split('/')[0]}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-gray-200 flex items-center">
        <button 
          onClick={() => {
            setRetryCount(0);
            fetchHistory();
          }} 
          className="text-sm text-blue-600 hover:text-blue-800"
        >
          🔄 Refresh
        </button>
        <span className="text-xs text-gray-500 ml-4">
          {uploads.length} file{uploads.length !== 1 && 's'}
        </span>
      </div>
    </div>
  );
};

export default UploadHistory;