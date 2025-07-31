import React, { useState, useCallback, ChangeEvent, FormEvent } from 'react';
import API from '../api/client.ts';
import { useAuth } from '../context/AuthContext.tsx';
import UploadHistory from '../components/media-uploader/UploadHistory.tsx';
import Sidebar from '../components/Sidebar.tsx';
import ToggleControl from '../components/media-uploader/ToggleControl.tsx';
import useFileUpload from '../hooks/useFileUpload.tsx';
import FileUploader from '../components/media-uploader/FileUploader.tsx';
import MediaList from '../components/media-uploader/MediaList.tsx';
import type { MediaFile, GeneratedMedia, Project} from '../../api/models.tsx';

// Allowed MIME types and size limits
const ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/webm'];
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const ALLOWED_AUDIO_TYPES = ['audio/mpeg', 'audio/wav'];
const MAX_FILE_SIZE = 50 * 2**20; // 50 MB

interface MediaUploaderProps {
  onUploadSuccess: (projectId: string) => void;
  onUploadError?: (errorMessage: string) => void;
}

const MediaUploader: React.FC<MediaUploaderProps> = ({ onUploadSuccess, onUploadError }) => {
  const { logout } = useAuth();
  const [activeSection, setActiveSection] = useState('upload');
  const [activeTab, setActiveTab] = useState('upload');
  //File states
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);

  // Error and loading states
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [uploadedFiles, setUploadedFiles] = useState<MediaFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<MediaFile | null>(null);
  const [generatedMedia] = useState<GeneratedMedia[]>([
    {
      id: '1',
      name: 'Generated Video 1',
      type: 'video',
      createdAt: new Date('2024-01-20'),
      status: 'completed',
      url: '/generated-video-1.mp4'
    }
  ]);

  const { isUploading, uploadProgress } = useFileUpload();
  
  const handleFileUpload = (file: MediaFile) => {
    setUploadedFiles(prev => [file, ...prev]);
  };

  const handlePublish = (platform: string) => {
    console.log(`Publishing to ${platform}:`, {
      file: selectedFile,
      // In production, this would send to your API
    });
    alert(`Successfully scheduled post to ${platform}!`);
  };


  // Counter to trigger history refresh
  const [historyRefreshTrigger, setHistoryRefreshTrigger] = useState<number>(0);

  const validateFile = useCallback((file: File, allowedTypes: string[]) => {
    if (!allowedTypes.includes(file.type)) {
      return `Invalid file type: ${file.type}`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File exceeds ${MAX_FILE_SIZE / 2**20} MB limit`;
    }
    return null;
  }, []);

  const onChangeFactory = useCallback((
    setter: React.Dispatch<React.SetStateAction<File | null>>,
    types: string[]
  ) => (e: ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const file = e.target.files?.[0] ?? null;
    if (file) {
      const err = validateFile(file, types);
      if (err) return setError(err);
      setter(file);
    }
  }, [validateFile]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!videoFile || !audioFile) {
      setError('Both video and audio files are required.');
      return;
    }

    const formData = new FormData();
    formData.append('video', videoFile);
    formData.append('audio', audioFile);
    if (thumbnailFile) formData.append('thumbnail', thumbnailFile);

    try {
      setLoading(true);
      const res = await API.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const { project_id } = res.data;
      
      // Clear form on success
      setVideoFile(null);
      setAudioFile(null);
      setThumbnailFile(null);
      
      // Clear file inputs
      const form = e.target as HTMLFormElement;
      const fileInputs = form.querySelectorAll('input[type="file"]') as NodeListOf<HTMLInputElement>;
      fileInputs.forEach(input => input.value = '');
      
      // Trigger history refresh
      setHistoryRefreshTrigger(prev => prev + 1);
      
      // Call parent callback
      onUploadSuccess(project_id);
    } catch (err: any) {
      if (err.response) {
        const status = err.response.status;
        if (status === 401) {
          // Session expired or unauthorized
          logout();
          return;
        }
        if (status === 415) {
          setError('Unsupported file type.');
        } else if (status === 500) {
          setError('Server error saving files.');
        } else {
          setError(err.response.data.detail || 'Upload failed.');
        }
      } else {
        setError(err.message || 'Unexpected error occurred.');
      }
      onUploadError?.(error || 'Upload error');
    } finally {
      setLoading(false);
    }
  };

  // Handle project selection from history
  const handleProjectSelect = useCallback((projectId: string) => {
    console.log('Selected project:', projectId);
    // TODO: Implement project details view or navigation
    // For now, just call the parent callback to maintain compatibility
    onUploadSuccess(projectId);
  }, [onUploadSuccess]);

  return (
    <div className="flex min-h-screen bg-gradient-to-br from-[#17183D] via-[#2C275C] to-[#10123B] text-gray-800">
      <Sidebar />
  
      <main className="flex-1 p-6 space-y-6">
        {activeSection === 'upload' && (
          <div className="max-w-6xl mx-auto space-y-8">
            <div className="flex justify-between items-center">
              <h1 className="text-3xl font-bold text-white">Media Management</h1>
              {/* <DatabaseDropdown onSelect={setSelectedFile} /> */}
            </div>
  
            <ToggleControl
              options={[
                { id: 'upload', label: 'Upload Media' },
                { id: 'generate', label: 'Generate Media' },
              ]}
              active={activeTab}
              onChange={setActiveTab}
            />
  
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Left Column */}
              <div className="space-y-8">
                {activeTab === 'upload' && (
                  <>
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                      {/* Upload Form */}
                      <form
                        onSubmit={handleSubmit}
                        className="bg-white rounded-lg shadow-lg p-6 space-y-6"
                      >
                        <h2 className="text-2xl font-bold text-gray-900">
                          Upload Media
                        </h2>
                        <div className="grid grid-cols-1 gap-6">
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
                              <AlertCircle
                                size={16}
                                className="text-red-500"
                              />
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
                              Uploading... {uploadProgress}%
                            </span>
                          ) : (
                            'Upload & Generate'
                          )}
                        </button>
                      </form>
  
                      {/* Upload History */}
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
                  </>
                )}
  
                {activeTab === 'generate' && (
                  <div className="bg-white rounded-lg shadow-lg p-6">
                    <h3 className="text-xl font-bold text-gray-900 mb-4">
                      Generate History
                    </h3>
                    <div className="text-center py-8 text-gray-500">
                      <PlusCircle
                        size={48}
                        className="mx-auto mb-4 opacity-50"
                      />
                      <p>Generated media will appear here</p>
                    </div>
                  </div>
                )}
              </div>
  
              {/* Right Column */}
              <div className="bg-white rounded-lg shadow-lg p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-6">
                  Video Manipulation & Publish
                </h3>
                <VideoManipulationPanel
                  videoFile={videoFile}
                  audioFile={audioFile}
                  thumbnailFile={thumbnailFile}
                  onPublish={handlePublish}
                />
              </div>
            </div>
          </div>
        )}
  
        {activeSection !== 'upload' && (
          <div className="max-w-4xl mx-auto text-center py-16">
            <div className="text-gray-400 mb-4">
              <PlusCircle size={64} className="mx-auto" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2 capitalize">
              {activeSection}
            </h2>
            <p className="text-gray-300">This section is coming soon!</p>
          </div>
        )}
      </main>
    </div>
  );
  
    
export default MediaUploader;