// src/components/ProgressBar/ProgressBar.tsx
import React from 'react';

interface ProgressBarProps {
  progress: number; // 0–100
}

const ProgressBar: React.FC<ProgressBarProps> = ({ progress }) => (
  <div aria-label="Upload progress" className="w-full bg-gray-200 rounded-lg h-3 overflow-hidden">
    <div
      className="h-full rounded-lg transition-all duration-300"
      style={{ width: `${progress}%`, backgroundColor: '#4F46E5' }}
    />
  </div>
);

export default ProgressBar;
