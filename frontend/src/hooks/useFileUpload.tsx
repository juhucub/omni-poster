import { useState, useCallback } from 'react';

const useFileUpload = () => {
    const [isUploading, setIsUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
  
    const uploadFile = useCallback(async (file: File, type: string) => {
      setIsUploading(true);
      setUploadProgress(0);
      setError(null);
  
      try {
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
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        clearInterval(progressInterval);
        setUploadProgress(100);
        
        // Mock successful upload
        return {
          id: Date.now().toString(),
          name: file.name,
          type: type as 'video' | 'audio' | 'thumbnail',
          size: file.size,
          url: URL.createObjectURL(file),
          uploadedAt: new Date()
        };
      } catch (err) {
        setError('Upload failed. Please try again.');
        throw err;
      } finally {
        setIsUploading(false);
        setTimeout(() => setUploadProgress(0), 1000);
      }
    }, []);
  
    return { uploadFile, isUploading, uploadProgress, error };
  };

export default useFileUpload;