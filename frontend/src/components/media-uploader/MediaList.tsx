import React, { useState } from 'react';
import { FileText, Video, Music, Image, Check } from 'lucide-react';
import type { MediaFile } from '../../types/media';

interface MediaListProps {
  files: MediaFile[];
  onSelect: (f: MediaFile) => void;
  selectedFile?: MediaFile;
}

const MediaList: React.FC<MediaListProps> = ({ files, onSelect, selectedFile }) => {
  const [sortBy, setSortBy] = useState<'date' | 'name'>('date');
  const sorted = [...files].sort((a,b) => sortBy==='date'
    ? b.uploadedAt.getTime() - a.uploadedAt.getTime()
    : a.name.localeCompare(b.name)
  );

  if (!files.length) return (
    <div className="text-center py-8 text-gray-500">
      <FileText size={48} className="mx-auto opacity-50" />
      <p>No uploads</p>
    </div>
  );

  return (
    <div>
      <div className="flex justify-between mb-2">
        <h3 className="font-medium text-gray-900">History</h3>
        <select value={sortBy} onChange={e => setSortBy(e.target.value as any)} className="border px-2 py-1">
          <option value="date">Date</option>
          <option value="name">Name</option>
        </select>
      </div>
      <div className="space-y-2">
        {sorted.map(f => (
          <button key={f.id} onClick={() => onSelect(f)} className={`flex items-center p-2 rounded-lg ${selectedFile?.id===f.id ? 'bg-blue-50 border-blue-500' : 'border-gray-200'}`}>
            {f.type==='video' && <Video size={20} className="text-red-500" />}
            {f.type==='audio' && <Music size={20} className="text-green-500" />}
            {f.type==='thumbnail' && <Image size={20} className="text-blue-500" />}
            <div className="ml-2 flex-1 text-left">
              <p className="truncate">{f.name}</p>
              <p className="text-xs text-gray-500">{f.uploadedAt.toLocaleDateString()}</p>
            </div>
            {selectedFile?.id===f.id && <Check size={16} className="text-blue-500" />}
          </button>
        ))}
      </div>
    </div>
  );
};

export default MediaList;