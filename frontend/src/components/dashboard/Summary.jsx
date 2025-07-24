import React from 'react';
import { Youtube, Instagram, Annoyed } from 'lucide-react';

const Summary = () => {
  const actions = [
    { icon: <Annoyed />, label: 'TikTok' , color: 'text-blue-500'},
    { icon: <Instagram />, label: 'Instagram' , color: 'text-pink-500'},
    { icon: <Youtube />, label: 'YouTube', color: 'text-red-500' }
  ];

  const prompts = ['Create', 'Schedule', 'Post', 'Automate'];
  
  return (
    <section className="bg-gradient-to-br from-[#10123B] to-[#17183D] rounded-lg border-2 border-white shadow-md p-6">
      <h3 className="text-xl font-semibold mb-4 text-white bebas-neue">I want to...</h3>
      <div className="flex flex-wrap gap-4 mb-6">
        {prompts.map((prompt, index) => (
          <button
            key={index}
            className="bg-purple-600 text-white px-4 py-2 rounded-full hover:bg-purple-600 transition"
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