import React, { useState, useCallback, ChangeEvent, FormEvent } from 'react';
import API from '../api/client.ts';
import { useAuth } from '../context/AuthContext.tsx';
import UploadHistory from '../components/media-uploader/UploadHistory.tsx';
import Sidebar from '../components/Sidebar.tsx';
import ToggleControl from '../components/media-uploader/ToggleControl.tsx';
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
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  
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
        <ToggleControl 
          options={[
            { id: 'upload', label: 'Upload Media' },
            { id: 'generate', label: 'Generate Media' }
          ]} 
          active={''} onChange={function (id: string): void {
          throw new Error('Function not implemented.');
        } } />
      {/* Upload Form */}
      <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-white rounded-lg shadow">
        <h2 className="text-xl font-semibold">Upload Media</h2>

        <div>
          <label className="block text-sm font-medium">Video File</label>
          <input
            type="file"
            accept={ALLOWED_VIDEO_TYPES.join(',')}
            onChange={onChangeFactory(setVideoFile, ALLOWED_VIDEO_TYPES)}
            required
            className="mt-1 block w-full text-sm border border-gray-300 rounded-md p-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          {videoFile && (
            <p className="text-xs text-gray-600 mt-1">
              Selected: {videoFile.name} ({(videoFile.size / (1024 * 1024)).toFixed(1)} MB)
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium">Audio File</label>
          <input
            type="file"
            accept={ALLOWED_AUDIO_TYPES.join(',')}
            onChange={onChangeFactory(setAudioFile, ALLOWED_AUDIO_TYPES)}
            required
            className="mt-1 block w-full text-sm border border-gray-300 rounded-md p-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          {audioFile && (
            <p className="text-xs text-gray-600 mt-1">
              Selected: {audioFile.name} ({(audioFile.size / (1024 * 1024)).toFixed(1)} MB)
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium">Thumbnail (optional)</label>
          <input
            type="file"
            accept={ALLOWED_IMAGE_TYPES.join(',')}
            onChange={onChangeFactory(setThumbnailFile, ALLOWED_IMAGE_TYPES)}
            className="mt-1 block w-full text-sm border border-gray-300 rounded-md p-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          {thumbnailFile && (
            <p className="text-xs text-gray-600 mt-1">
              Selected: {thumbnailFile.name} ({(thumbnailFile.size / (1024 * 1024)).toFixed(1)} MB)
            </p>
          )}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-md p-3">
            <p className="text-red-600 text-sm">{error}</p>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Uploading...
            </span>
          ) : (
            'Upload & Generate'
          )}
        </button>
      </form>

      {/* Upload History */}
      <UploadHistory 
        onSelect={handleProjectSelect}
        refreshTrigger={historyRefreshTrigger}
      />
    </main>
    </div>
  );
};

export default MediaUploader;