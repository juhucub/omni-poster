// src/components/UploadPlatform/VideoManipulationPanel.tsx
import React, { useState } from 'react';
import { 
  Video, 
  Music, 
  Image,
  RotateCcw,
  Crop,
  Type,
  Check
} from 'lucide-react';
import { sanitizeInput } from '../../utils/security';

interface VideoManipulationPanelProps {
  videoFile: File | null;
  audioFile: File | null;
  thumbnailFile: File | null;
  onPublish: (platform: string) => void;
}

const VideoManipulationPanel: React.FC<VideoManipulationPanelProps> = ({ 
  videoFile, 
  audioFile, 
  thumbnailFile, 
  onPublish 
}) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [resolution, setResolution] = useState('1080p');

  const isVideoReady = title.trim() && description.trim() && videoFile && audioFile;
  const videoUrl = videoFile ? URL.createObjectURL(videoFile) : null;

  return (
    <div className="space-y-6">
      {/* Video Preview */}
      <div className="bg-black rounded-lg aspect-video flex items-center justify-center relative overflow-hidden">
        {videoUrl ? (
          <video 
            src={videoUrl} 
            className="w-full h-full object-contain"
            controls
          />
        ) : (
          <div className="text-white text-center">
            <Video size={48} className="mx-auto mb-4 opacity-50" />
            <p>Upload a video to preview</p>
          </div>
        )}
      </div>

      {/* File Status */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`p-3 rounded-lg border ${videoFile ? 'border-green-200 bg-green-50' : 'border-gray-200'}`}>
          <div className="flex items-center space-x-2">
            <Video size={16} className={videoFile ? 'text-green-500' : 'text-gray-400'} />
            <span className="text-sm font-medium">
              {videoFile ? 'Video Ready' : 'Video Required'}
            </span>
            {videoFile && <Check size={14} className="text-green-500" />}
          </div>
        </div>
        
        <div className={`p-3 rounded-lg border ${audioFile ? 'border-green-200 bg-green-50' : 'border-gray-200'}`}>
          <div className="flex items-center space-x-2">
            <Music size={16} className={audioFile ? 'text-green-500' : 'text-gray-400'} />
            <span className="text-sm font-medium">
              {audioFile ? 'Audio Ready' : 'Audio Required'}
            </span>
            {audioFile && <Check size={14} className="text-green-500" />}
          </div>
        </div>
        
        <div className={`p-3 rounded-lg border ${thumbnailFile ? 'border-green-200 bg-green-50' : 'border-gray-200'}`}>
          <div className="flex items-center space-x-2">
            <Image size={16} className={thumbnailFile ? 'text-green-500' : 'text-gray-400'} />
            <span className="text-sm font-medium">
              {thumbnailFile ? 'Thumbnail Ready' : 'Thumbnail Optional'}
            </span>
            {thumbnailFile && <Check size={14} className="text-green-500" />}
          </div>
        </div>
      </div>

      {/* Video Controls */}
      <div className="flex space-x-2">
        <button 
          disabled={!videoFile}
          className="flex items-center space-x-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <RotateCcw size={16} />
          <span>Trim</span>
        </button>
        <button 
          disabled={!videoFile}
          className="flex items-center space-x-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Crop size={16} />
          <span>Crop</span>
        </button>
        <button 
          disabled={!videoFile}
          className="flex items-center space-x-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Type size={16} />
          <span>Text</span>
        </button>
      </div>

      {/* Metadata Inputs */}
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Title <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(sanitizeInput(e.target.value))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter video title"
            maxLength={100}
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Description <span className="text-red-500">*</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(sanitizeInput(e.target.value))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            rows={3}
            placeholder="Enter video description"
            maxLength={500}
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tags</label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(sanitizeInput(e.target.value))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter tags separated by commas"
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Resolution</label>
          <select
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="720p">720p HD</option>
            <option value="1080p">1080p Full HD</option>
            <option value="4k">4K Ultra HD</option>
          </select>
        </div>
      </div>

      {/* Publish Buttons */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <button
          onClick={() => onPublish('tiktok')}
          disabled={!isVideoReady}
          className="bg-black text-white px-4 py-3 rounded-lg hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          Post to TikTok
        </button>
        <button
          onClick={() => onPublish('instagram')}
          disabled={!isVideoReady}
          className="bg-gradient-to-r from-purple-600 to-pink-600 text-white px-4 py-3 rounded-lg hover:from-purple-700 hover:to-pink-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          Post to Instagram
        </button>
        <button
          onClick={() => onPublish('youtube')}
          disabled={!isVideoReady}
          className="bg-red-600 text-white px-4 py-3 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          Post to YouTube
        </button>
      </div>
    </div>
  );
};

export default VideoManipulationPanel;