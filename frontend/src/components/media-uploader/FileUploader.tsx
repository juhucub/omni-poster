import React, { useState, useRef, useCallback } from 'react';
import useFileUpload from '../../hooks/useFileUpload';
import { Video, Music, Image } from 'lucide-react';
// Utility functions with security
const sanitizeInput = (input: string): string => {
  return input.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
              .replace(/[<>]/g, '');
};

const validateFileType = (file: File, allowedTypes: string[]): boolean => {
  return allowedTypes.some(type => file.type.startsWith(type));
};

const validateFileSize = (file: File, maxSizeMB: number): boolean => {
  return file.size <= maxSizeMB * 1024 * 1024;
};


const FileUploader: React.FC<{
  fileType: 'video' | 'audio' | 'thumbnail';
  onUpload: (file: File) => void;
  isUploading: boolean;
  progress: number;
}> = ({ fileType, onUpload, isUploading, progress }) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { uploadFile } = useFileUpload();

  const fileConfig = {
    video: { 
      accept: 'video/*', 
      maxSize: 100, 
      icon: Video, 
      label: 'Video Files',
      description: 'MP4, AVI, MOV up to 100MB'
    },
    audio: { 
      accept: 'audio/*', 
      maxSize: 50, 
      icon: Music, 
      label: 'Audio Files',
      description: 'MP3, WAV, AAC up to 50MB'
    },
    thumbnail: { 
      accept: 'image/*', 
      maxSize: 10, 
      icon: Image, 
      label: 'Thumbnail Images',
      description: 'PNG, JPG, GIF up to 10MB'
    }
  };

  const config = fileConfig[fileType];
  const Icon = config.icon;

  const handleFile = async (file: File) => {
    if (!validateFileType(file, [config.accept.split('/')[0]])) {
      alert(`Invalid file type. Please select a ${config.label.toLowerCase()}.`);
      return;
    }

    if (!validateFileSize(file, config.maxSize)) {
      alert(`File too large. Maximum size is ${config.maxSize}MB.`);
      return;
    }

    try {
      const uploadedFile = await uploadFile(file, fileType);
      onUpload(uploadedFile);
    } catch (error) {
      console.error('Upload failed:', error);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      handleFile(files[0]);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  }

  return (
    <div className="space-y-4">
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragging 
            ? 'border-blue-500 bg-blue-50' 
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <Icon size={48} className="mx-auto mb-4 text-gray-400" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">{config.label}</h3>
        <p className="text-gray-500 mb-4">{config.description}</p>
        
        {isUploading ? (
          <div className="space-y-2">
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-sm text-gray-600">Uploading... {progress}%</p>
          </div>
        ) : (
          <>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Browse Files
            </button>
            <p className="text-sm text-gray-500 mt-2">or drag and drop files here</p>
          </>
        )}
        
        <input
          ref={fileInputRef}
          type="file"
          accept={config.accept}
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>
    </div>
  );
};

export default FileUploader;