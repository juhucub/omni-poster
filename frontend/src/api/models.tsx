// Auto-generated TypeScript interfaces based on Python Pydantic models

/**
 * Response when uploading media assets
 */
export interface UploadResponse {
  project_id: string;
  message: string;
}

export type FileType = 'video' | 'audio' | 'thumbnail';
  
  /**
   * Authentication token response
   */
  export interface TokenResponse {
    access_token: string;
    token_type: "bearer";
  }
  
  /**
   * Basic user information
   */
  export interface UserResponse {
    id: number;
    username: string;
  }
  
  /**
   * Request payload for user registration
   */
  export interface RegisterRequest {
    username: string; // at least 3 characters, alphanumeric or underscore
    password: string; // at least 8 characters, with upper, lower, digit
  }
  
  /**
   * Request payload for user login
   */
  export interface LoginRequest {
    username: string; // at least 3 characters
    password: string; // at least 8 characters
  }
  
  /**
   * Internal re-authentication request (same shape as LoginRequest)
   */
  export interface MeRequest {
    username: string;
    password: string;
  }
  
  /**
   * Response from /auth/me including new token
   */
  export interface MeResponse extends UserResponse {
    access_token: string;
    token_type: "bearer";
  }
  
  /**
   * Payload to create a social account via OAuth
   */
  export interface AccountCreate {
    platform: 'youtube' | 'tiktok' | 'instagram';
    oauth_code: string;
  }
  
  /**
   * Representation of a linked social account
   */
  export interface AccountOut {
    id: number;
    platform: string;
    name: string;
    profile_picture: string; // HttpUrl
    stats: Record<string, number>; // e.g. { followers: 1000, views: 5000 }
    status: 'authorized' | 'token_expired' | 'rate_warning';
  }
  
  /**
   * Metrics fetched from a social account
   */
  export interface MetricsOut {
    followers: number;
    views: number;
    likes: number;
  }
  
  /**
   * Payload to set or update goals for a social account
   */
  export interface GoalIn {
    views?: number;
    likes?: number;
    followers?: number;
  }
  
  /**
   * Generic message wrapper for simple success/failure messages
   */
  export interface Message {
    detail: string;
  }
  
  // src/types/video.ts

/** Basic metadata for a generated video */
export interface Metadata {
  /** Human-readable title (max ~100 chars) */
  title: string;
  /** Description or summary (max ~500 chars) */
  description: string;
  /** Array of tag strings, e.g. ["promo","tutorial"] */
  tags: string[];
}

/** Supported output resolutions */
export type Resolution = '720p' | '1080p' | '4k';

/** Generation options beyond metadata */
export interface VideoOptions {
  /** Desired resolution for the final video */
  resolution: Resolution;
}

export interface MediaFile {
  id: string;
  name: string;
  type: 'video' | 'audio' | 'thumbnail';
  size: number;
  url: string;
  uploadedAt: Date;
  duration?: number;
  dimensions?: { width: number; height: number };
}

export interface GeneratedMedia {
  id: string;
  name: string;
  type: string;
  createdAt: Date;
  status: 'processing' | 'completed' | 'failed';
  url?: string;
}

export interface Project {
  project_id: string;
  video_name: string;
  audio_name: string;
  thumbnail_name?: string;
  created_at: string;
  status: string;
}

export interface UploadRecord {
  project_id: string;
  filename: string;
  url: string;
  content_type: string;
  uploader_id: string;
  uploaded_at: string;
}

export interface UploadContextType {
  uploads: UploadRecord[];
  loading: boolean;
  error: string | null;
  addUpload: (upload: UploadRecord) => void;
  removeUpload: (projectId: string, filename: string) => void;
  refreshUploads: () => Promise<void>;
  lastUpdated: Date | null;
}