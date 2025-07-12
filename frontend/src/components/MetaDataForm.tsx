import React, { useState, ChangeEvent, FormEvent } from 'react';
import axios from 'axios';

interface MetadataFormProps {
  /** The project ID associated with this metadata */
  projectId: string;
  /** Callback invoked when metadata is successfully saved */
  onComplete: (metadata: {
    title: string;
    tags: string[];
    hashtags: string[];
  }) => void;
}

/**
 * MetadataForm
 * Collects Title, Tags, and Hashtags for a video project.
 * Sanitizes inputs, enforces simple validation, and posts to backend.
 */
const MetadataForm: React.FC<MetadataFormProps> = ({ projectId, onComplete }) => {
  const [title, setTitle] = useState<string>('');
  const [tagsInput, setTagsInput] = useState<string>('');
  const [hashtagsInput, setHashtagsInput] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // Utility: remove any HTML tags to prevent XSS
  const sanitize = (input: string) => input.replace(/<[^>]*>/g, '');

  // Utility: split comma-separated values into trimmed, non-empty array
  const parseList = (input: string) =>
    input
      .split(',')
      .map(item => item.trim())
      .filter(item => item.length > 0);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanTitle = sanitize(title).trim();
    if (cleanTitle.length === 0) {
      setError('Title is required.');
      return;
    }
    if (cleanTitle.length > 100) {
      setError('Title must be under 100 characters.');
      return;
    }

    const tags = parseList(tagsInput);
    if (tags.length > 10) {
      setError('Maximum of 10 tags allowed.');
      return;
    }

    let hashtags = parseList(hashtagsInput).map(tag => {
      const clean = tag.replace(/^#*/, ''); // strip leading '#'
      return `#${clean}`;
    });
    if (hashtags.length > 10) {
      setError('Maximum of 10 hashtags allowed.');
      return;
    }

    const payload = {
      project_id: projectId,
      title: cleanTitle,
      tags,
      hashtags,
    };

    try {
      setLoading(true);
      // POST metadata to backend endpoint
      await axios.post('/metadata', payload, {
        headers: { 'Content-Type': 'application/json' },
        withCredentials: true, // include CSRF/auth tokens
      });
      onComplete({ title: cleanTitle, tags, hashtags });
    } catch (err: any) {
      setError('Failed to save metadata. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-white rounded shadow" noValidate>
      <h2 className="text-xl font-semibold">Metadata</h2>

      {/* Title Input */}
      <div>
        <label htmlFor="title" className="block text-sm font-medium">
          Title <span className="text-red-500">*</span>
        </label>
        <input
          id="title"
          name="title"
          type="text"
          value={title}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
          maxLength={100}
          required
          className="mt-1 block w-full border border-gray-300 rounded p-2 focus:outline-none focus:ring focus:border-blue-300"
        />
      </div>

      {/* Tags Input */}
      <div>
        <label htmlFor="tags" className="block text-sm font-medium">
          Tags (comma-separated)
        </label>
        <input
          id="tags"
          name="tags"
          type="text"
          value={tagsInput}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setTagsInput(e.target.value)}
          placeholder="e.g. travel, tutorial, cooking"
          className="mt-1 block w-full border border-gray-300 rounded p-2 focus:outline-none focus:ring focus:border-blue-300"
        />
        <p className="text-gray-500 text-xs mt-1">Up to 10 tags, separated by commas.</p>
      </div>

      {/* Hashtags Input */}
      <div>
        <label htmlFor="hashtags" className="block text-sm font-medium">
          Hashtags (comma-separated)
        </label>
        <input
          id="hashtags"
          name="hashtags"
          type="text"
          value={hashtagsInput}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setHashtagsInput(e.target.value)}
          placeholder="e.g. #fun #video"
          className="mt-1 block w-full border border-gray-300 rounded p-2 focus:outline-none focus:ring focus:border-blue-300"
        />
        <p className="text-gray-500 text-xs mt-1">Up to 10 hashtags. '#' prefix optional.</p>
      </div>

      {/* Error message */}
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={loading}
        className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? 'Saving...' : 'Save Metadata'}
      </button>
    </form>
  );
};

export default MetadataForm;
