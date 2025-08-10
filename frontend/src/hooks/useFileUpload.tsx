import { useState, useCallback } from 'react';
import API from '../api/client';

interface UploadResponse {
  success: boolean;
  files: {
    video: string;
    audio: string;
    thumbnail?: string;
  };
  project_id: string;
  message: string;
}

const useFileUpload = () => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const uploadFiles = useCallback(async (
    videoFile: File | null,
    audioFile: File | null,
    thumbnailFile?: File | null
  ): Promise<UploadResponse | null> => {
    if (!videoFile || !audioFile) {
      setError('Both video and audio files are required.');
      return null;
    }

    setIsUploading(true);
    setError(null);
    setUploadProgress(0);

    try {
      // Create form data
      const formData = new FormData();
      formData.append('video', videoFile);
      formData.append('audio', audioFile);
      if (thumbnailFile) {
        formData.append('thumbnail', thumbnailFile);
      }

      console.log('Uploading files:', {
        video: videoFile.name,
        audio: audioFile.name,
        thumbnail: thumbnailFile?.name
      });

      // Make the upload request
      const response = await API.post<UploadResponse>('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 300000, // 5 minutes for large files
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percentCompleted);
            console.log(`Upload progress: ${percentCompleted}%`);
          }
        }
      });
      
      console.log('Full response from server:', response);
      console.log('Response data:', response.data);
      
      // Check if response exists and has data
      if (!response || !response.data) {
        console.error('No response data received from server');
        throw new Error('No response data received from server');
      }
      
      // Validate response structure
      if (!response.data.project_id) {
        console.error('Response missing project_id. Actual response:', response.data);
        throw new Error('Invalid response from server - missing project_id');
      }
      
      setUploadProgress(100);
      return response.data;
      
    } catch (err: any) {
      console.error('Upload error:', err);

      // Fixed: Changed 'error' to 'err' throughout the catch block
      if (err.response?.status === 404) {
        setError('Upload endpoint not found. Check if the backend server is running.');
      } else if (err.response?.status === 422) {
        const details = err.response.data?.detail || [];
        const errorMsg = Array.isArray(details) 
          ? details.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join(', ')
          : 'Invalid file format or data';
        setError(`Validation error: ${errorMsg}`);
      } else if (err.response?.status === 413) {
        setError('File too large. Please check file size limits.');
      } else if (err.response?.status === 415) {
        setError('Unsupported file type. Please check the allowed file formats.');
      } else if (err.response?.status === 500) {
        setError('Server error. Please try again later.');
      } else if (err.response?.data?.detail) {
        setError(err.response.data.detail);
      } else if (err.message) {
        setError(err.message);
      } else {
        setError('Upload failed. Please try again.');
      }
      
      return null;

    } finally {
      setIsUploading(false);
    }
  }, []);

  const resetUpload = useCallback(() => {
    setIsUploading(false);
    setUploadProgress(0);
    setError(null);
  }, []);
  
  return { uploadFiles, isUploading, uploadProgress, error, resetUpload };
};

export default useFileUpload;