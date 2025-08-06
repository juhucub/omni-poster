import { useState, useCallback } from 'react';
import API from '../api/client';

interface UseFileUploadReturn {
  uploadProject: (videoFile: File, audioFile: File, thumbnailFile?: File) => Promise<{ project_id: string; message: string }>;
  isUploading: boolean;
  uploadProgress: number;
  error: string | null;
}

const useFileUpload = (): UseFileUploadReturn => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const uploadProject = useCallback(async (
    videoFile: File,
    audioFile: File,
    thumbnailFile?: File
  ): Promise<{ project_id: string; message: string }> => {
    setIsUploading(true);
    setUploadProgress(0);
    setError(null);

    console.log('🚀 Starting upload with files:', {
      video: { name: videoFile.name, size: videoFile.size, type: videoFile.type },
      audio: { name: audioFile.name, size: audioFile.size, type: audioFile.type },
      thumbnail: thumbnailFile ? { name: thumbnailFile.name, size: thumbnailFile.size, type: thumbnailFile.type } : null
    });

    try {
      // Create form data
      const formData = new FormData();
      formData.append('video', videoFile);
      formData.append('audio', audioFile);
      if (thumbnailFile) {
        formData.append('thumbnail', thumbnailFile);
      }

      // Simulate upload progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 200);

      console.log('🌐 Making API request to /upload...');

      // THE KEY FIX: Override Content-Type for this specific request
      const response = await API.instance.post('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
          // Axios will automatically set the boundary
        },
        timeout: 300000, // 5 minutes for large files
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            console.log(`📈 Upload progress: ${percentCompleted}%`);
            setUploadProgress(Math.min(percentCompleted, 90));
          }
        }
      });
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      
      console.log('✅ Upload successful:', response.data);
      
      // Your backend returns: { project_id, urls, status }
      return {
        project_id: response.data.project_id,
        message: response.data.status || 'Upload successful'
      };
      
    } catch (err: any) {
      console.error('❌ Upload error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        headers: err.response?.headers
      });

      let errorMessage = 'Upload failed';

      if (err.response) {
        const status = err.response.status;
        const data = err.response.data;
        
        switch (status) {
          case 401:
            errorMessage = 'Authentication required. Please log in.';
            break;
          case 413:
            errorMessage = 'File too large. Maximum size is 500MB per file.';
            break;
          case 415:
            errorMessage = 'Unsupported file type. Please check file formats.';
            break;
          case 422:
            errorMessage = data.detail || 'Invalid file data.';
            break;
          case 500:
            errorMessage = 'Server error. Please try again later.';
            break;
          default:
            errorMessage = data.detail || `Server error (${status})`;
        }
      } else if (err.request) {
        errorMessage = 'Network error. Please check your connection.';
      } else if (err.code === 'ECONNABORTED') {
        errorMessage = 'Upload timeout. Please try again.';
      } else {
        errorMessage = err.message || 'Unexpected error occurred.';
      }

      setError(errorMessage);
      throw new Error(errorMessage);
      
    } finally {
      setIsUploading(false);
      setTimeout(() => setUploadProgress(0), 1000);
    }
  }, []);

  return { uploadProject, isUploading, uploadProgress, error };
};

export default useFileUpload;