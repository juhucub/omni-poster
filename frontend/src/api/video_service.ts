// src/api/video_service.ts
import { useState, useCallback } from 'react';
import API from './client';

export interface Metadata {
  title: string;
  description: string;
  tags: string[];
}

export interface VideoOptions {
  resolution: '720p' | '1080p' | '4k';
}

export interface UseVideoUploadReturn {
  file: File | null;
  setFile: (file: File | null) => void;
  metadata: Metadata;
  setMetadata: (metadata: Metadata) => void;
  options: VideoOptions;
  setOptions: (options: VideoOptions) => void;
  uploadProgress: number;
  previewUrl: string | null;
  generateVideo: () => Promise<void>;
  isGenerating: boolean;
  error: string | null;
}

// This should be a HOOK, not an async function
export const useVideoUpload = (): UseVideoUploadReturn => {
  const [file, setFile] = useState<File | null>(null);
  const [metadata, setMetadata] = useState<Metadata>({
    title: '',
    description: '',
    tags: [],
  });
  const [options, setOptions] = useState<VideoOptions>({
    resolution: '1080p',
  });
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const generateVideo = useCallback(async () => {
    if (!file) {
      setError('Please select a file first');
      return;
    }

    try {
      setIsGenerating(true);
      setError(null);
      setUploadProgress(0);

      // Create form data
      const formData = new FormData();
      formData.append('video', file);
      formData.append('metadata', JSON.stringify(metadata));
      formData.append('options', JSON.stringify(options));

      // Upload with progress tracking
      const response = await API.post('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            setUploadProgress(progress);
          }
        },
      });

      // Get the project ID and generate video
      const { project_id } = response.data;
      
      // Call generate endpoint
      const generateResponse = await API.post('/generate_video', {
        project_id,
        metadata,
        options,
      });

      // Set preview URL
      setPreviewUrl(generateResponse.data.video_url);
    } catch (err: any) {
      console.error('Video generation failed:', err);
      setError(
        err.response?.data?.detail || 
        err.message || 
        'Failed to generate video'
      );
    } finally {
      setIsGenerating(false);
    }
  }, [file, metadata, options]);

  return {
    file,
    setFile,
    metadata,
    setMetadata,
    options,
    setOptions,
    uploadProgress,
    previewUrl,
    generateVideo,
    isGenerating,
    error,
  };
};