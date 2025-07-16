import React from 'react';

export const CreateAccount: React.FC = () => {
  const startOAuth = (platform: string) => {
    window.location.href = `/auth/${platform}`; 
    // your backend OAuth kickoff endpoint
  };

  return (
    <div className="space-x-4">
      {['youtube','tiktok','instagram'].map(p => (
        <button
          key={p}
          onClick={() => startOAuth(p)}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Connect {p.charAt(0).toUpperCase()+p.slice(1)}
        </button>
      ))}
    </div>
  );
};
