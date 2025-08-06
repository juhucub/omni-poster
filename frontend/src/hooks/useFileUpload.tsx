import { useState, useCallback } from 'react';
import API from '../api/client';

interface UploadResponse {
  success: boolean, 
  files: {
    video: string,
    audio: string,
    thumbnail?: string
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
    if(!videoFile || !audioFile) {
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
      if (thumbnailFile)  formData.append('thumbnail', thumbnailFile);

      // Simulate upload progress
      const data = await API.instance.post<UploadResponse>('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 300000, // 5 minutes for large files
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percentCompleted);
          }
        }
      });
      
      return data.data;
      
    } catch (err: any) {
      console.error('upload error!', err);

      if (error.data?.status === 404) {
        setError('Upload endpoint not found. Check if the backend server is running.');
      } else if (error.data?.status === 422) {
        const details = error.data.data?.detail || [];
        const errorMsg = Array.isArray(details) 
          ? details.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join(', ')
          : 'Invalid file format or data';
        setError(`Validation error: ${errorMsg}`);
      } else if (error.data?.status === 413) {
        setError('File too large. Please check file size limits.');
      } else {
        setError(error.data?.data?.detail || error.message || 'Upload failed');
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