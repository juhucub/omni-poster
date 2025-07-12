import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface UploadHistoryItem {
  project_id: string;
  title: string;
  platforms: string[];
  scheduled_time: string; // ISO string
  status: 'uploaded' | 'processing' | 'ready' | 'uploading' | 'completed' | 'failed';
  created_at: string;   // ISO string
}

/**
 * UploadHistoryTable
 * Fetches and displays a history of upload jobs.
 * Shows project ID, title, platforms, scheduled time, status, and creation date.
 * Handles loading, errors, and empty state.
 */
const UploadHistoryTable: React.FC = () => {
  const [history, setHistory] = useState<UploadHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        setLoading(true);
        const response = await axios.get<UploadHistoryItem[]>('/history', {
          withCredentials: true, // include auth/CSRF cookies
        });
        setHistory(response.data);
      } catch (err: any) {
        console.error('Failed to fetch upload history:', err);
        setError('Unable to load upload history.');
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, []);

  if (loading) {
    return (
      <div className="p-4 flex items-center space-x-2">
        <svg
          className="animate-spin h-5 w-5 text-gray-600"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
          />
        </svg>
        <span className="text-gray-600">Loading upload history...</span>
      </div>
    );
  }

  if (error) {
    return <div className="p-4 bg-red-100 text-red-700 rounded">{error}</div>;
  }

  if (history.length === 0) {
    return <div className="p-4 text-gray-500">No uploads found yet.</div>;
  }

  return (
    <div className="overflow-x-auto p-4 bg-white rounded shadow">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Project ID</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Platforms</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Scheduled</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Created At</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {history.map((item) => (
            <tr key={item.project_id} className="hover:bg-gray-50">
              <td className="px-4 py-2 text-sm text-gray-700 font-mono truncate max-w-xs">{item.project_id}</td>
              <td className="px-4 py-2 text-sm text-gray-700">{item.title}</td>
              <td className="px-4 py-2 text-sm text-gray-700">
                {item.platforms.join(', ')}
              </td>
              <td className="px-4 py-2 text-sm text-gray-700">
                {new Date(item.scheduled_time).toLocaleString()}
              </td>
              <td className="px-4 py-2 text-sm">
                <span
                  className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                    item.status === 'completed'
                      ? 'bg-green-100 text-green-800'
                      : item.status === 'failed'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}
                >
                  {item.status}
                </span>
              </td>
              <td className="px-4 py-2 text-sm text-gray-700">
                {new Date(item.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default UploadHistoryTable;
