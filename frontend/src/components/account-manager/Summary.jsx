import React from 'react';
import { FaInstagram, FaTiktok, FaYoutube } from 'react-icons/fa';

const Summary = () => {
  const actions = [
    { icon: <FaTiktok />, label: 'TikTok', color: 'text-pink-500' },
    { icon: <FaInstagram />, label: 'Instagram', color: 'text-purple-500' },
    { icon: <FaYoutube />, label: 'YouTube', color: 'text-red-500' }
  ];

  const prompts = ['Create', 'Post', 'Schedule', 'Automate'];

  return (
    <section className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-xl font-semibold mb-4">I want to...</h3>
      <div className="flex flex-wrap gap-4 mb-6">
        {prompts.map((prompt, index) => (
          <button
            key={index}
            className="bg-blue-100 text-blue-700 px-4 py-2 rounded-full hover:bg-blue-200 transition"
          >
            {prompt}
          </button>
        ))}
      </div>
      <div className="flex gap-6">
        {actions.map((action, index) => (
          <div
            key={index}
            className={`flex items-center space-x-3 px-4 py-3 rounded-lg bg-gray-50 shadow-inner hover:bg-gray-100 cursor-pointer ${action.color}`}
          >
            <span className="text-xl">{action.icon}</span>
            <span className="font-medium text-gray-700">{action.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
};

export default Summary;