import React, { FC, createContext, useEffect, useContext, useState, useCallback, ReactNode } from 'react';
import API from '../../api/client.ts';
import { useAuth } from '../../context/AuthContext';


interface UploadRecord {
  project_id: string;
  filename: string;
  url: string;
  content_type: string;
  uploader_id: string;
  uploaded_at: string;
}

interface UploadContextType {
  uploads: UploadRecord[];
  loading: boolean;
  error: string | null;
  addUpload: (upload: UploadRecord) => void;
  removeUpload: (projectId: string, filename: string) => void;
  refreshUploads: () => Promise<void>;
  lastUpdated: Date | null;
}

const UploadContext = createContext<UploadContextType>({
  uploads: [],
  loading: false,
  error: null,
  addUpload: () => {},
  removeUpload: () => {},
  refreshUploads: async () => {},
  lastUpdated: null,
});


export const UploadProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refreshUploads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await API.get<UploadRecord[]>('/upload_history');
      setUploads(response.data);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch uploads');
      throw err; // Re-throw for component handling
    } finally {
      setLoading(false);
    }
  }, []);

  const addUpload = useCallback((newUpload: UploadRecord) => {
    console.log('Adding upload to context:', newUpload);
    setUploads(prev => {
      // Check if upload already exists to avoid duplicates
      const exists = prev.some(u => 
        u.project_id === newUpload.project_id && u.filename === newUpload.filename
      );
      if (exists) return prev;
      
      // Add new upload and sort by upload date (newest first)
      const updated = [...prev, newUpload].sort(
        (a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
      );
      return updated;
    });
    setLastUpdated(new Date());
  }, []);

  const removeUpload = useCallback((projectId: string, filename: string) => {
    setUploads(prev => 
      prev.filter(u => !(u.project_id === projectId && u.filename === filename))
    );
    setLastUpdated(new Date());
  }, []);

  const value = {
    uploads,
    loading,
    error,
    addUpload,
    removeUpload,
    refreshUploads,
    lastUpdated,
  };

  return <UploadContext.Provider value={value}>{children}</UploadContext.Provider>;
};

interface UploadHistoryProps {
  onSelect: (projectId: string) => void;
}

export const useUploadHistory = () => {
  const context = useContext(UploadContext);
  if (!context) {
    throw new Error('useUploadHistory must be used within an UploadProvider');
  }
  return context;
};

const UploadHistory: FC<UploadHistoryProps> = ({ onSelect }) => {
  const { isAuthenticated, isLoading: authLoading, logout } = useAuth();
  const { 
    uploads, 
    loading, 
    error, 
    refreshUploads, 
    lastUpdated 
  } = useUploadHistory();

  // Only fetch on mount or when authentication changes
  useEffect(() => {
    if (authLoading) return;
    
    if (isAuthenticated && uploads.length === 0) {
      console.log('UploadHistory: Initial load');
      refreshUploads().catch(err => {
        if (err.response?.status === 401) {
          console.log('UploadHistory: Authentication failed, logging out');
          logout();
        }
      });
    }
  }, [isAuthenticated, authLoading, uploads.length, refreshUploads, logout]);

  // Manual refresh function
  const handleRefresh = async () => {
    try {
      await refreshUploads();
    } catch (err: any) {
      if (err.response?.status === 401) {
        logout();
      }
    }
  };

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

  if (loading && uploads.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          <span className="ml-2 text-gray-600">Loading history…</span>
        </div>
      </div>
    );
  }

  if (error && uploads.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <span className="text-red-400">⚠️</span>
            <div className="ml-3">
              <h4 className="text-sm font-medium text-red-800">Error loading history</h4>
              <p className="text-sm text-red-700 mt-1">{error}</p>
              <button
                onClick={handleRefresh}
                className="mt-2 text-sm bg-red-100 hover:bg-red-200 text-red-800 px-3 py-1 rounded border border-red-300"
              >
                Try Again
              </button>
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
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Upload History</h3>
        {lastUpdated && (
          <span className="text-xs text-gray-500">
            Updated {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>
      
      <div className="space-y-2">
        {uploads.map((upload, i) => (
          <div
            key={`${upload.project_id}-${upload.filename}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(upload.project_id)}
            onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onSelect(upload.project_id)}
            className={`
              p-3 rounded-md border cursor-pointer transition-colors
              ${i % 2 === 0 ? 'bg-gray-50' : 'bg-white'}
              hover:bg-blue-50 hover:border-blue-200 border-gray-200
            `}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3 flex-1 min-w-0">
                <span className="text-xl">{iconFor(upload.content_type)}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{upload.filename}</p>
                  <p className="text-xs text-gray-500 truncate">Project: {upload.project_id}</p>
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-xs text-gray-500">{formatTimestamp(upload.uploaded_at)}</p>
                <p className="text-xs text-gray-400 capitalize">{upload.content_type.split('/')[0]}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-4 pt-3 border-t border-gray-200 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button 
            onClick={handleRefresh}
            disabled={loading}
            className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
          >
            {loading ? '⏳ Refreshing...' : '🔄 Refresh'}
          </button>
          <span className="text-xs text-gray-500">
            {uploads.length} file{uploads.length !== 1 && 's'}
          </span>
        </div>
        {error && (
          <span className="text-xs text-red-500">
            ⚠️ {error}
          </span>
        )}
      </div>
    </div>
  );
};

export default UploadHistory;