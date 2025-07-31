import { useState, useCallback } from 'react';
import API from '../api/client.ts';

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
  
      try {
        //Save form data
        const formFata = new FormData();
        formFata.append('video', videoFile);
        formFata.append('audio', audioFile);
        if (thumbnailFile) {
          formFata.append('thumbnail', thumbnailFile);
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
  
        // Simulate API call
        const response = await API.post('/projects/upload', formFata, {
            headers: {
                'Content-Type': 'multipart/form-data'
                //FIXME: CSRF projection and JWT auth headers will be added by API client
                },
            });
        
        clearInterval(progressInterval);
        setUploadProgress(100);
        
        return response.data;
        } catch(err: any) {
            if (err.response) {
                const status = err.response.status;
                if (status === 415) {
                  setError('Unsupported file type.');
                } else if (status === 500) {
                  setError('Server error saving files.');
                } else if (status === 413) {
                  setError('File too large.');
                } else {
                  setError(err.response.data.detail || 'Upload failed.');
                }
              } else {
                setError(err.message || 'Network error occurred.');
              }
        throw err;
        } finally {
            setIsUploading(false);
            setTimeout(() => setUploadProgress(0), 1000);
        }
          }, []);
        
          return { uploadProject, isUploading, uploadProgress, error };
        };
export default useFileUpload;