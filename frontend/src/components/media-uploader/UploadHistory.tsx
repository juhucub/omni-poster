import React, { FC, useState, useEffect, useCallback, useMemo } from 'react';
import API from '../../api/client.ts';
import { useAuth } from '../../context/AuthContext.tsx';

// Type definition matching the backend response
interface UploadRecord {
  project_id: string;
  filename: string;
  url: string;
  content_type: string;
  uploader_id: string;
  uploaded_at: string; // ISO timestamp
}

interface UploadHistoryProps {
  onSelect: (projectId: string) => void;
  refreshTrigger?: number; // Optional prop to trigger refresh from parent
}

const UploadHistory: React.FC<UploadHistoryProps> = ({ onSelect, refreshTrigger }) => {
  const { logout } = useAuth();
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch upload history from backend
  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await API.get<UploadRecord[]>('/upload_history');
      setUploads(response.data);
    } catch (err: any) {
      if (err.response?.status === 401) {
        // Session expired - logout user
        logout();
        return;
      }
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to fetch upload history';
      setError(errorMsg);
      console.error('Error fetching upload history:', err);
    } finally {
      setLoading(false);
    }
  }, [logout]);

  // Fetch on mount
  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Refresh when refreshTrigger changes (e.g., after successful upload)
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      fetchHistory();
    }
  }, [refreshTrigger, fetchHistory]);

  // Sort uploads chronologically (newest first)
  const sortedUploads = useMemo(() => {
    return [...uploads].sort((a, b) => 
      new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
    );
  }, [uploads]);

  // Format timestamp for display
  const formatTimestamp = useCallback((isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'Invalid date';
    }
  }, []);

  // Get file type icon based on content type
  const getFileIcon = useCallback((contentType: string) => {
    if (contentType.startsWith('video/')) return '🎥';
    if (contentType.startsWith('audio/')) return '🎵';
    if (contentType.startsWith('image/')) return '🖼️';
    return '📄';
  }, []);

  // Handle item click
  const handleItemClick = useCallback((projectId: string) => {
    onSelect(projectId);
  }, [onSelect]);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4">Upload History</h3>
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-gray-600">Loading history...</span>
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
            <div className="flex-shrink-0">
              <span className="text-red-400">⚠️</span>
            </div>
            <div className="ml-3">
              <h4 className="text-sm font-medium text-red-800">Error loading history</h4>
              <p className="text-sm text-red-700 mt-1">{error}</p>
              <button
                onClick={fetchHistory}
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

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold mb-4">Upload History</h3>
      
      {sortedUploads.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <div className="text-4xl mb-2">📤</div>
          <p>No uploads yet</p>
          <p className="text-sm">Your uploaded files will appear here</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sortedUploads.map((upload, index) => (
            <div
              key={`${upload.project_id}-${upload.filename}`}
              className={`
                p-3 rounded-md border transition-colors cursor-pointer
                ${index % 2 === 0 ? 'bg-gray-50' : 'bg-white'}
                hover:bg-blue-50 hover:border-blue-200
                border-gray-200
              `}
              onClick={() => handleItemClick(upload.project_id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleItemClick(upload.project_id);
                }
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3 flex-1 min-w-0">
                  <span className="text-xl flex-shrink-0">
                    {getFileIcon(upload.content_type)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {upload.filename}
                    </p>
                    <p className="text-xs text-gray-500 truncate">
                      Project: {upload.project_id}
                    </p>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right">
                  <p className="text-xs text-gray-500">
                    {formatTimestamp(upload.uploaded_at)}
                  </p>
                  <p className="text-xs text-gray-400 capitalize">
                    {upload.content_type.split('/')[0]}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      
      {sortedUploads.length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-200">
          <button
            onClick={fetchHistory}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            🔄 Refresh
          </button>
          <span className="text-xs text-gray-500 ml-4">
            {sortedUploads.length} file{sortedUploads.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}
    </div>
  );
};

export default UploadHistory;