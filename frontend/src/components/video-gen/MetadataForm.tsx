import React, { useState, KeyboardEvent } from 'react';
import type { Metadata } from '../../types/video';

interface MetadataFormProps {
  metadata: Metadata;
  onChange: (metadata: Metadata) => void;
}

const MetadataForm: React.FC<MetadataFormProps> = ({ metadata, onChange }) => {
  const [tagInput, setTagInput] = useState('');

  const addTag = () => {
    const tag = tagInput.trim();
    if (tag && !metadata.tags.includes(tag)) {
      onChange({ ...metadata, tags: [...metadata.tags, tag] });
    }
    setTagInput('');
  };

  const removeTag = (tag: string) => {
    onChange({ ...metadata, tags: metadata.tags.filter(t => t !== tag) });
  };

  return (
    <div className="bg-white p-4 rounded-2xl shadow-sm space-y-4">
      <div>
        <label htmlFor="title" className="block text-sm font-medium text-gray-700">
          Title
        </label>
        <input
          id="title"
          type="text"
          value={metadata.title}
          onChange={e => onChange({ ...metadata, title: e.target.value })}
          className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
          maxLength={100}
        />
      </div>

      <div>
        <label htmlFor="description" className="block text-sm font-medium text-gray-700">
          Description
        </label>
        <textarea
          id="description"
          value={metadata.description}
          onChange={e => onChange({ ...metadata, description: e.target.value })}
          className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
          rows={4}
          maxLength={500}
        />
      </div>

      <div>
        <label htmlFor="tags" className="block text-sm font-medium text-gray-700">
          Tags
        </label>
        <div className="flex flex-wrap gap-2 mt-1">
          {metadata.tags.map(tag => (
            <span
              key={tag}
              className="flex items-center bg-indigo-100 text-indigo-800 px-2 py-1 rounded-full text-xs"
            >
              {tag}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="ml-1 focus:outline-none"
                aria-label={`Remove ${tag}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <input
          id="tags"
          type="text"
          value={tagInput}
          onChange={e => setTagInput(e.target.value)}
          onKeyDown={(e: KeyboardEvent) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addTag();
            }
          }}
          placeholder="Press Enter to add tag"
          className="mt-2 block w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
      </div>
    </div>
  );
};

export default MetadataForm;
