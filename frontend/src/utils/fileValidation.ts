// src/utils/fileValidation.ts

// File validation constants
export const ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/webm', 'video/avi', 'video/mov'];
export const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
export const ALLOWED_AUDIO_TYPES = ['audio/mpeg', 'audio/wav', 'audio/aac', 'audio/mp3'];

export const MAX_VIDEO_SIZE = 100 * 1024 * 1024; // 100MB
export const MAX_AUDIO_SIZE = 50 * 1024 * 1024; // 50MB
export const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB

/**
 * Validates if a file type is allowed for the given category
 */
export const validateFileType = (file: File, allowedTypes: string[]): boolean => {
  return allowedTypes.includes(file.type);
};

/**
 * Validates if a file size is within the allowed limit
 */
export const validateFileSize = (file: File, maxSize: number): boolean => {
  return file.size <= maxSize;
};

/**
 * Comprehensive file validation for upload types
 */
export const validateFile = (file: File, type: 'video' | 'audio' | 'thumbnail'): string | null => {
  const configs = {
    video: { 
      types: ALLOWED_VIDEO_TYPES, 
      maxSize: MAX_VIDEO_SIZE,
      label: 'video'
    },
    audio: { 
      types: ALLOWED_AUDIO_TYPES, 
      maxSize: MAX_AUDIO_SIZE,
      label: 'audio'
    },
    thumbnail: { 
      types: ALLOWED_IMAGE_TYPES, 
      maxSize: MAX_IMAGE_SIZE,
      label: 'image'
    }
  };
  
  const config = configs[type];
  
  if (!validateFileType(file, config.types)) {
    return `Invalid file type: ${file.type}. Allowed ${config.label} types: ${config.types.join(', ')}`;
  }
  
  if (!validateFileSize(file, config.maxSize)) {
    const maxSizeMB = config.maxSize / (1024 * 1024);
    return `File exceeds ${maxSizeMB}MB limit. Current size: ${(file.size / (1024 * 1024)).toFixed(1)}MB`;
  }
  
  return null;
};

/**
 * Get human-readable file size
 */
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

/**
 * Get file extension from filename
 */
export const getFileExtension = (filename: string): string => {
  return filename.slice((filename.lastIndexOf('.') - 1 >>> 0) + 2);
};

/**
 * Check if file is an image
 */
export const isImageFile = (file: File): boolean => {
  return file.type.startsWith('image/');
};

/**
 * Check if file is a video
 */
export const isVideoFile = (file: File): boolean => {
  return file.type.startsWith('video/');
};

/**
 * Check if file is an audio file
 */
export const isAudioFile = (file: File): boolean => {
  return file.type.startsWith('audio/');
};