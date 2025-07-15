// File: src/components/Sidebar.jsx
import React from 'react';
import { FaTachometerAlt, FaVideo, FaUsersCog, FaCalendarAlt, FaCog, FaQuestionCircle } from 'react-icons/fa';

const navItems = [
  { icon: <FaTachometerAlt />, label: 'Dashboard' },
  { icon: <FaVideo />, label: 'Media Creator' },
  { icon: <FaUsersCog />, label: 'Account(s) Manager' },
  { icon: <FaCalendarAlt />, label: 'Upload Schedule' },
  { icon: <FaCog />, label: 'Settings' }
];

const Sidebar = () => {
  return (
    <aside className="w-64 bg-white shadow-md p-6 flex flex-col justify-between">
      <div>
        <h1 className="text-2xl font-bold mb-8 text-blue-600">omniposter</h1>
        <nav className="space-y-4">
          {navItems.map((item, idx) => (
            <div key={idx} className="flex items-center space-x-3 text-gray-700 hover:text-blue-600 cursor-pointer">
              <span className="text-lg">{item.icon}</span>
              <span>{item.label}</span>
            </div>
          ))}
        </nav>
      </div>
      <div className="text-sm text-gray-500 mt-8">
        <div className="mb-1">© 2025</div>
        <a href="#" className="flex items-center space-x-1 text-blue-500 hover:underline">
          <FaQuestionCircle />
          <span>Help Link</span>
        </a>
      </div>
    </aside>
  );
};

export default Sidebar;
