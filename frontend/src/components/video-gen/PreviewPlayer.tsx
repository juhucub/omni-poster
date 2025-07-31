import React from 'react';

interface PreviewPlayerProps {
  src: string;
}

const PreviewPlayer: React.FC<PreviewPlayerProps> = ({ src }) => (
  <video
    src={src}
    controls
    className="w-full rounded-2xl shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
    aria-label="Video preview"
  />
);

export default PreviewPlayer;
