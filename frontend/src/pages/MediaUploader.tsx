import React, { useState, useCallback, ChangeEvent, FormEvent } from 'react';
import API from '../api/client';
import { useAuth } from '../context/AuthContext';
import UploadHistory from '../components/media-uploader/UploadHistory';
import Sidebar from '../components/Sidebar';
import ToggleControl from '../components/media-uploader/ToggleControl';
import useFileUpload from '../hooks/useFileUpload';
import FileUploader from '../components/media-uploader/FileUploader';
import MediaList from '../components/media-uploader/MediaList';
import VideoManipulationPanel from '../components/media-uploader/VideoManipulationPanel';
import type { MediaFile, GeneratedMedia } from '../types/media';
import { AlertCircle, PlusCircle, RefreshCw } from 'lucide-react';

// Allowed MIME types and size limits
const ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/webm'];
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const ALLOWED_AUDIO_TYPES = ['audio/mpeg', 'audio/wav'];
const MAX_FILE_SIZE = 50 * 2 ** 20; // 50 MB

interface MediaUploaderProps {
  onUploadSuccess: (projectId: string) => void;
  onUploadError?: (errorMessage: string) => void;
}

const MediaUploader: React.FC<MediaUploaderProps> = ({ onUploadSuccess, onUploadError }) => {
  const { logout } = useAuth();
  const [activeSection, setActiveSection] = useState('upload');
  const [activeTab, setActiveTab] = useState('upload');

  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);
  
  const [error, setError] = useState<string | null>(null);
  const [historyRefreshTrigger, setHistoryRefreshTrigger] = useState(0);
  const [uploadedFiles, setUploadedFiles] = useState<MediaFile[]>([]);

  const { isUploading, uploadProgress } = useFileUpload();

  // Handle upload from drag/drop or browse
  const handleFileUpload = useCallback((file: MediaFile) => {
    setUploadedFiles(prev => [file, ...prev]);
  }, []);

  const handleProjectSelect = useCallback(
    (projectId: string) => onUploadSuccess(projectId),
    [onUploadSuccess]
  );

  const onChangeFactory = useCallback(
    (
      setter: React.Dispatch<React.SetStateAction<File | null>>,
      types: string[]
    ) => (e: ChangeEvent<HTMLInputElement>) => {
      setError(null);
      const file = e.target.files?.[0] ?? null;
      if (file) {
        const err = !types.includes(file.type)
          ? `Invalid file type: ${file.type}`
          : file.size > MAX_FILE_SIZE
            ? `File exceeds ${MAX_FILE_SIZE / 2 ** 20} MB limit`
            : null;
        if (err) return setError(err);
        setter(file);
      }
    },
    []
  );

  //Upload files to backend
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!videoFile || !audioFile) {
      setError('Both video and audio files are required.');
      return;
    }

    const totalSize = videoFile.size + audioFile.size + (thumbnailFile?.size || 0);
    if (totalSize > MAX_FILE_SIZE) {
      setError(`Total upload size exceeds ${MAX_FILE_SIZE / 2 ** 20} MB limit.`);
      return;
    }
    //FIXME: add Uploading state
    
    try {
      const formData = new FormData();
      formData.append('video', videoFile);
      formData.append('audio', audioFile);
      if (thumbnailFile) formData.append('thumbnail', thumbnailFile);
  
      //FIXME: Simulate Progress
      

      const data = await API.instance.post<{ project_id: string }>(
        '/upload',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      setVideoFile(null);
      setAudioFile(null);
      setThumbnailFile(null);
      setHistoryRefreshTrigger(t => t + 1);
      setUploadedFiles(prev => [
        ...prev,
        { id: data.project_id, name: '', type: 'video', size: 0, url: '', uploadedAt: new Date() }
      ]);
      onUploadSuccess(data.project_id);
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

  return (
    <div className="flex min-h-screen bg-gradient-to-br from-[#17183D] via-[#2C275C] to-[#10123B] text-gray-800">
      <Sidebar activeSection={activeSection} onSectionChange={setActiveSection} />

      <main className="flex-1 p-6 space-y-6">
        {activeSection === 'upload' ? (
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
              <div className="space-y-8">
                {activeTab === 'upload' && (
                  <div className="grid xl:grid-cols-2 gap-8">
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

                      {error && (
                        <div className="bg-red-50 border border-red-200 rounded-md p-3">
                          <div className="flex items-center space-x-2">
                            <AlertCircle size={16} className="text-red-500" />
                            <p className="text-red-600 text-sm">{error}</p>
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

                    <div className="bg-white rounded-lg shadow-lg p-6">
                      <UploadHistory
                        uploads={uploadedFiles}
                        loading={false}
                        error={null}
                        onSelect={handleProjectSelect}
                        onRefresh={() => setHistoryRefreshTrigger(t => t + 1)}
                        lastUpdated={historyRefreshTrigger}
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

              <div className="bg-white rounded-lg shadow-lg p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-6">Video Manipulation & Publish</h3>
                <VideoManipulationPanel
                  videoFile={videoFile}
                  audioFile={audioFile}
                  thumbnailFile={thumbnailFile}
                  onPublish={() => {} }
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto text-center py-16">
            <div className="text-gray-400 mb-4">
              <PlusCircle size={64} className="mx-auto" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2 capitalize">{activeSection}</h2>
            <p className="text-gray-300">This section is coming soon!</p>
          </div>
        )}
      </main>
    </div>
  );
};

export default MediaUploader;
function setLoading(arg0: boolean) {
  throw new Error('Function not implemented.');
}

