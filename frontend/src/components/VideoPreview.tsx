import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface VideoPreviewProps {
  projectId: string;
  pollIntervalMs?: number; // Interval to poll status, default 3000ms
  onReady: () => void; // Callback when video is ready
}

const VideoPreview: React.FC<VideoPreviewProps> = ({ projectId, pollIntervalMs = 3000 }) => {
  // Component state
  const [status, setStatus] = useState<'processing' | 'ready' | 'failed' | 'idle'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  useEffect(() => {
    let intervalId: NodeJS.Timeout;
    let mounted = true;

    // Function to fetch job status
    const fetchStatus = async () => {
      try {
        const response = await axios.get('/get-status', {
          params: { job_id: projectId },
          withCredentials: true, // Ensure auth/CSRF cookies are sent
        });
        const jobStatus = response.data.status;

        if (!mounted) return;
        setStatus(jobStatus);

        if (jobStatus === 'ready') {
          // Construct the video playback URL
          // Assumes the backend serves at /videos/{projectId}_final.mp4
          setVideoUrl(`/videos/${projectId}_final.mp4`);
          clearInterval(intervalId);
          onReady(); // Notify parent component that video is ready
        } else if (jobStatus === 'failed') {
          setError('Video processing failed. Please try again.');
          clearInterval(intervalId);
        }
      } catch (err: any) {
        if (!mounted) return;
        setError('Error fetching status.');
        clearInterval(intervalId);
      }
    };

    // Kick off polling
    setStatus('processing');
    fetchStatus();
    intervalId = setInterval(fetchStatus, pollIntervalMs);

    // Cleanup on unmount
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [onReady, projectId, pollIntervalMs]);

  // Render UI based on state
  if (error) {
    return <div className="p-4 bg-red-100 text-red-700 rounded">{error}</div>;
  }

  if (status === 'processing' || status === 'idle') {
    return (
      <div className="p-4 flex items-center space-x-2">
        <svg
          className="animate-spin h-5 w-5 text-blue-600"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
          />
        </svg>
        <span className="text-blue-600">Processing video...</span>
      </div>
    );
  }

  if (status === 'ready' && videoUrl) {
    return (
      <div className="p-4 bg-white rounded shadow">
        <h2 className="text-lg font-medium mb-2">Video Preview</h2>
        <video
          src={videoUrl}
          controls
          className="w-full rounded"
        >
          Your browser does not support the video tag.
        </video>
      </div>
    );
  }

  return null; // Fallback
};

export default VideoPreview;
