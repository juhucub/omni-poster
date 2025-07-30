// src/components/GenerateButton/GenerateButton.tsx
import React from 'react';

interface GenerateButtonProps {
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
}

const GenerateButton: React.FC<GenerateButtonProps> = ({ onClick, disabled, loading }) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`
      inline-flex items-center px-6 py-2 rounded-lg text-white font-medium
      ${disabled
        ? 'bg-indigo-300 cursor-not-allowed'
        : 'bg-indigo-600 hover:bg-indigo-700 focus:ring-2 focus:ring-indigo-500'}
      focus:outline-none transition
    `}
    aria-label="Generate video"
  >
    {loading && (
      <svg
        className="animate-spin h-5 w-5 mr-2"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
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
    )}
    {loading ? 'Generating…' : 'Generate'}
  </button>
);

export default GenerateButton;
