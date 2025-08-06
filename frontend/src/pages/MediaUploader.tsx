import React, { useState, useCallback, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import UploadHistory from '../components/media-uploader/UploadHistory';
import Sidebar from '../components/Sidebar';
import ToggleControl from '../components/media-uploader/ToggleControl';
import useFileUpload from '../hooks/useFileUpload';
import FileUploader from '../components/media-uploader/FileUploader';
import VideoManipulationPanel from '../components/media-uploader/VideoManipulationPanel';
import type { UploadRecord } from '../api/models.tsx';
import { AlertCircle, PlusCircle, RefreshCw } from 'lucide-react';
import API from '../api/client.ts';

// Allowed MIME types and size limits
const MAX_FILE_SIZE = 50 * 2 ** 20; // 50 MB

interface MediaUploaderProps {
  onUploadSuccess: (projectId: string) => void;
  onUploadError?: (errorMessage: string) => void;
}

const MediaUploader: React.FC<MediaUploaderProps> = ({ onUploadSuccess, onUploadError }) => {
  const { logout } = useAuth();
  const [activeTab, setActiveTab] = useState('upload');

  //file states
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);
  
  //error state
  const [error, setError] = useState<string | null>(null);

  //upload history state
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const { uploadProject, isUploading, uploadProgress, error: uploadError } = useFileUpload();

  //Load Upload History
  const refreshUploads = useCallback(async () => {
    try {
      setHistoryLoading(true);
      setHistoryError(null);
      const data = await API.instance.get('/upload_history');
      setUploads(data.data);
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Error loading upload history:', err);
      setHistoryError(err.response?.data?.detail || 'Failed to load upload history');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  //FIXME: Load history on mount
  useEffect(() => {
    refreshUploads();
  }, [refreshUploads]);

  const handleProjectSelect = useCallback(
    (projectId: string) => onUploadSuccess(projectId),
    [onUploadSuccess]
  );

  //Upload files to backend
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!videoFile || !audioFile) {
      setError('Both video and audio files are required.');
      return;
    }
    //FIXME: add Uploading state
    
    try {
      console.log('Starting upload:');
     
      const result = await uploadProject(videoFile, audioFile, thumbnailFile);

      console.log('Upload success!!:');

      setVideoFile(null);
      setAudioFile(null);
      setThumbnailFile(null);

      await refreshUploads();

      //Notify parent
      onUploadSuccess(result.project_id);

    } catch (err: any) {
      if (err.response) {
        const status = err.response.status;
        if (status === 401) {
          logout();
          return;
        }
        if (status === 415) setError('Unsupported file type.');
        else if (status === 500) setError('Server error saving files.');
        else setError(err.response.data.detail || 'Upload failed.');
      } else {
        setError(err.message || 'Unexpected error occurred.');
      }
      onUploadError?.(error || 'Upload error');
    }
  };

  const handlePublish = (platform: string) => {
    console.log(`publishing to ${platform}:`, {
      video: videoFile?.name,
      audio: audioFile?.name,
      thumbnail: thumbnailFile?.name
    });
    alert(`Publishing to ${platform} is not implemented yet.`);
  };

  return (
    <div className="flex min-h-screen bg-gradient-to-br from-[#17183D] via-[#2C275C] to-[#10123B] text-gray-800">
      <Sidebar />

      <main className="flex-1 p-6 space-y-6">
          <div className="max-w-6xl mx-auto space-y-8">
            <div className="flex justify-between items-center">
              <h1 className="text-3xl font-bold text-white">Media Management</h1>
            </div>

            <ToggleControl
              options={[
                { id: 'upload', label: 'Upload Media' },
                { id: 'generate', label: 'Generate Media' }
              ]}
              active={activeTab}
              onChange={setActiveTab}
            />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              { /* :eft Column */ }
              <div className="space-y-8">
                {activeTab === 'upload' && (
                  <div className="grid xl:grid-cols-2 gap-8">
                    { /* File Upload Form */ } 
                    <form
                      onSubmit={handleSubmit}
                      className="bg-white rounded-lg shadow-lg p-6 space-y-6"
                    >
                      <h2 className="text-2xl font-bold text-gray-900">Upload Media</h2>
                      <div className="grid gap-6">
                        <FileUploader
                          fileType="video"
                          onFileSelect={setVideoFile}
                          selectedFile={videoFile}
                          required
                        />
                        <FileUploader
                          fileType="audio"
                          onFileSelect={setAudioFile}
                          selectedFile={audioFile}
                          required
                        />
                        <FileUploader
                          fileType="thumbnail"
                          onFileSelect={setThumbnailFile}
                          selectedFile={thumbnailFile}
                        />
                      </div>

                      {(error || uploadError) && (
                        <div className="bg-red-50 border border-red-200 rounded-md p-3">
                          <div className="flex items-center space-x-2">
                            <AlertCircle size={16} className="text-red-500" />
                            <p className="text-red-600 text-sm">{error || uploadError}</p>
                          </div>
                        </div>
                      )}

                      <button
                        type="submit"
                        disabled={isUploading || !videoFile || !audioFile}
                        className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                      >
                        {isUploading ? (
                          <span className="flex items-center justify-center">
                            <RefreshCw className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" />
                            Uploading… {uploadProgress}%
                          </span>
                        ) : (
                          'Upload & Generate'
                        )}
                      </button>
                    </form>

                    { /* Upload History */ }
                    <div className="bg-white rounded-lg shadow-lg p-6">
                      <UploadHistory
                        uploads={uploads}
                        loading={historyLoading}
                        error={historyError}
                        onSelect={handleProjectSelect}
                        onRefresh={refreshUploads}
                        lastUpdated={lastUpdated}
                      />
                    </div>
                  </div>
                )}

                {activeTab === 'generate' && (
                  <div className="bg-white rounded-lg shadow-lg p-6">
                    <h3 className="text-xl font-bold text-gray-900 mb-4">Generate History</h3>
                    <div className="text-center py-8 text-gray-500">
                      <PlusCircle size={48} className="mx-auto mb-4 opacity-50" />
                      <p>Generated media will appear here</p>
                    </div>
                  </div>
                )}
              </div>

              { /* Right Column */ }
              <div className="bg-white rounded-lg shadow-lg p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-6">Video Manipulation & Publish</h3>
                <VideoManipulationPanel
                  videoFile={videoFile}
                  audioFile={audioFile}
                  thumbnailFile={thumbnailFile}
                  onPublish={handlePublish}
                />
              </div>
            </div>
          </div>
      </main>
    </div>
  );
};

export default MediaUploader;


