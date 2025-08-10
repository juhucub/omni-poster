import React from 'react';

const ToggleControl: React.FC<{ 
    options: { id: string; label: string }[]; 
    active: string; 
    onChange: (id: string) => void 
  }> = ({ options, active, onChange }) => {
    return (
      <div className="relative bg-gray-100 rounded-lg p-1 flex">
        {options.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={`relative px-6 py-2 rounded-md transition-all duration-200 font-medium ${
              active === id
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    );
  };

  export default ToggleControl;