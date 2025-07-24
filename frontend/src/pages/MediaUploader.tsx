import React, { useState, ChangeEvent, FormEvent } from 'react';
import API from '../api/client.ts';
import { useAuth } from '../context/AuthContext.tsx';

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

  const validateFile = (file: File, allowedTypes: string[]) => {
    if (!allowedTypes.includes(file.type)) {
      return `Invalid file type: ${file.type}`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File exceeds ${MAX_FILE_SIZE / 2**20} MB limit`;
    }
    return null;
  };

  const onChangeFactory = (
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
  };

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

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-white rounded-lg shadow">
      <h2 className="text-xl font-semibold">Upload Media</h2>

      <div>
        <label className="block text-sm font-medium">Video File</label>
        <input
          type="file"
          accept={ALLOWED_VIDEO_TYPES.join(',')}
          onChange={onChangeFactory(setVideoFile, ALLOWED_VIDEO_TYPES)}
          required
          className="mt-1 block w-full text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium">Audio File</label>
        <input
          type="file"
          accept={ALLOWED_AUDIO_TYPES.join(',')}
          onChange={onChangeFactory(setAudioFile, ALLOWED_AUDIO_TYPES)}
          required
          className="mt-1 block w-full text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium">Thumbnail (optional)</label>
        <input
          type="file"
          accept={ALLOWED_IMAGE_TYPES.join(',')}
          onChange={onChangeFactory(setThumbnailFile, ALLOWED_IMAGE_TYPES)}
          className="mt-1 block w-full text-sm"
        />
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Uploading…' : 'Upload & Generate'}
      </button>
    </form>
  );
};

export default MediaUploader;