// src/components/UploadPlatform/UploadHistory.tsx
import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { UploadRecord } from '../../api/models.tsx';
import { 
  RefreshCw, 
  AlertCircle, 
  FileText, 
  ChevronRight 
} from 'lucide-react';

interface UploadHistoryProps {
  uploads: UploadRecord[];
  loading: boolean;
  error: string | null;
  onSelect: (projectId: string) => void;
  onRefresh: () => void;
  lastUpdated: Date | null;
}

const UploadHistory: React.FC<UploadHistoryProps> = ({ 
  uploads, 
  loading, 
  error, 
  onSelect, 
  onRefresh, 
  lastUpdated 
}) => {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

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

  if (authLoading) {
    return (
      <div className="text-center py-8">
        <RefreshCw size={48} className="mx-auto mb-4 opacity-50 animate-spin" />
        <p className="text-gray-600">Checking authentication…</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
        <div className="flex items-center space-x-2">
          <AlertCircle size={16} className="text-yellow-500" />
          <div>
            <h4 className="text-sm font-medium text-yellow-800">Authentication Required</h4>
            <p className="text-sm text-yellow-700 mt-1">Please log in to view upload history.</p>
          </div>
        </div>
      </div>
    );
  }

  if (loading && uploads.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <RefreshCw size={48} className="mx-auto mb-4 opacity-50 animate-spin" />
        <p>Loading upload history...</p>
      </div>
    );
  }

  if (error && uploads.length === 0) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4">
        <div className="flex items-center space-x-2">
          <AlertCircle size={16} className="text-red-500" />
          <div className="flex-1">
            <h4 className="text-sm font-medium text-red-800">Error loading history</h4>
            <p className="text-sm text-red-700 mt-1">{error}</p>
            <button
              onClick={onRefresh}
              className="mt-2 text-sm bg-red-100 hover:bg-red-200 text-red-800 px-3 py-1 rounded border border-red-300 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (uploads.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <FileText size={48} className="mx-auto mb-4 opacity-50" />
        <p className="font-medium">No uploads yet</p>
        <p className="text-sm">Your uploaded files will appear here.</p>
      </div>
    );
  }

  // Group uploads by project_id
  const projectGroups = uploads.reduce((acc, upload) => {
    if (!acc[upload.project_id]) {
      acc[upload.project_id] = [];
    }
    acc[upload.project_id].push(upload);
    return acc;
  }, {} as Record<string, UploadRecord[]>);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="font-medium text-gray-900">Upload History</h3>
        <div className="flex items-center space-x-2">
          {lastUpdated && (
            <span className="text-xs text-gray-500">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button 
            onClick={onRefresh}
            disabled={loading}
            className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50 transition-colors"
            title="Refresh upload history"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
      
      <div className="space-y-3">
        {Object.entries(projectGroups).map(([projectId, projectUploads]) => (
          <button
            key={projectId}
            onClick={() => onSelect(projectId)}
            className="w-full flex items-center justify-between p-4 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-colors text-left"
          >
            <div className="flex items-center space-x-3">
              <div className="flex -space-x-1">
                {projectUploads.map((upload, idx) => (
                  <span key={idx} className="text-lg">
                    {iconFor(upload.content_type)}
                  </span>
                ))}
              </div>
              
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900">Project {projectId}</p>
                <p className="text-sm text-gray-500">
                  {projectUploads.length} file{projectUploads.length !== 1 ? 's' : ''} • {formatTimestamp(projectUploads[0].uploaded_at)}
                </p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {projectUploads.map((upload, idx) => (
                    <span key={idx} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                      {upload.filename}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            
            <ChevronRight size={16} className="text-gray-400" />
          </button>
        ))}
      </div>
      
      <div className="pt-3 border-t border-gray-200 flex items-center justify-between text-xs text-gray-500">
        <span>{uploads.length} file{uploads.length !== 1 ? 's' : ''} in {Object.keys(projectGroups).length} project{Object.keys(projectGroups).length !== 1 ? 's' : ''}</span>
        {error && (
          <span className="text-red-500 flex items-center space-x-1">
            <AlertCircle size={12} />
            <span>{error}</span>
          </span>
        )}
      </div>
    </div>
  );
};

export default UploadHistory;