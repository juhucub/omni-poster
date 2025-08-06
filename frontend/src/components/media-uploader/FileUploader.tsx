import React, { useState, useRef, useCallback } from 'react';
import { Video, Music, Image, AlertCircle } from 'lucide-react';

// File validation constants matching your backend
const ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/webm'];
const ALLOWED_AUDIO_TYPES = ['audio/mpeg', 'audio/wav', 'audio/mp3'];
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif'];

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

const validateFileType = (file: File, allowedTypes: string[]): boolean => {
  return allowedTypes.includes(file.type);
};

const validateFileSize = (file: File, maxSize: number): boolean => {
  return file.size <= maxSize;
};

const validateFile = (file: File, type: 'video' | 'audio' | 'thumbnail'): string | null => {
  const configs = {
    video: { types: ALLOWED_VIDEO_TYPES, maxSize: MAX_FILE_SIZE },
    audio: { types: ALLOWED_AUDIO_TYPES, maxSize: MAX_FILE_SIZE },
    thumbnail: { types: ALLOWED_IMAGE_TYPES, maxSize: MAX_FILE_SIZE }
  };
  
  const config = configs[type];
  
  if (!validateFileType(file, config.types)) {
    return `Invalid file type: ${file.type}. Allowed: ${config.types.join(', ')}`;
  }
  
  if (!validateFileSize(file, config.maxSize)) {
    return `File exceeds ${config.maxSize / (1024 * 1024)}MB limit`;
  }
  
  return null;
};
interface FileUploaderProps {
  fileType: 'video' | 'audio' | 'thumbnail';
  onFileSelect: (file: File | null) => void;
  selectedFile: File | null;
  required?: boolean;
}

const FileUploader: React.FC<FileUploaderProps> = ({ 
  fileType, 
  onFileSelect, 
  selectedFile, 
  required = false 
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fileConfig = {
    video: { 
      accept: ALLOWED_VIDEO_TYPES.join(','), 
      maxSize: MAX_FILE_SIZE, 
      icon: Video, 
      label: 'Video Files',
      description: 'MP4, WebM up to 50MB'
    },
    audio: { 
      accept: ALLOWED_AUDIO_TYPES.join(','), 
      maxSize: MAX_FILE_SIZE, 
      icon: Music, 
      label: 'Audio Files',
      description: 'MP3, WAV up to 50MB'
    },
    thumbnail: { 
      accept: ALLOWED_IMAGE_TYPES.join(','), 
      maxSize: MAX_FILE_SIZE, 
      icon: Image, 
      label: 'Thumbnail Images',
      description: 'PNG, JPG, GIF up to 50MB'
    }
  };

  const config = fileConfig[fileType];
  const Icon = config.icon;

  const handleFile = useCallback((file: File) => {
    console.log(`Validating ${fileType} file:`, {
      name: file.name,
      type: file.type,
      size: file.size,
      sizeInMB: (file.size / (1024 * 1024)).toFixed(2)
    });

    const validationError = validateFile(file, fileType);
    if (validationError) {
      console.error(`Validation failed for ${fileType}:`, validationError);
      setError(validationError);
      return;
    }
    
    console.log(`✓ ${fileType} file validation passed`);
    setError(null);
    onFileSelect(file);
  }, [fileType, onFileSelect]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      handleFile(files[0]);
    }
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file) {
      handleFile(file);
    }
  };

  const handleRemove = useCallback(() => {
    onFileSelect(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [onFileSelect]);

  const handleBrowse = useCallback(() => {
    fileInputRef.current?.click();
  }, []);


  return (
    <div className="space-y-4">
      <div
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-all duration-200 cursor-pointer ${
          isDragging 
            ? 'border-blue-500 bg-blue-50' 
            : selectedFile
            ? 'border-green-400 bg-green-50'
            : error
            ? 'border-red-300 bg-red-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={!selectedFile ? handleBrowse : undefined}
      >
        <Icon size={40} className={`mx-auto mb-3 ${
          selectedFile 
            ? 'text-green-500' 
            : error
            ? 'text-red-400'
            : 'text-gray-400'
          }`} />
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          {config.label} {required && <span className="text-red-500">*</span>}
        </h3>
        <p className="text-gray-500 mb-4">{config.description}</p>
        
        {selectedFile ? (
          <div className="space-y-2">
            <p className="text-sm font-medium text-green-600">
              ✓ {selectedFile.name}
            </p>
            <p className="text-xs text-gray-500">
              {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB • {selectedFile.type}
            </p>
            <div className="flex space-x-2 justify-center">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleBrowse();
                }}
                className="text-blue-600 hover:text-blue-700 text-sm font-medium"
              >
                Change File
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleRemove();
                }}
                className="text-red-600 hover:text-red-700 text-sm font-medium"
              >
                Remove
              </button>
            </div>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={handleBrowse}
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
      
      {error && (
        <div className="flex items-center space-x-2 text-red-600 text-sm">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
};

export default FileUploader;