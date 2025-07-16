// File: src/components/Sidebar.jsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  FaTachometerAlt,
  FaVideo,
  FaUsersCog,
  FaCalendarAlt,
  FaCog,
  FaQuestionCircle
} from 'react-icons/fa';

const navItems = [
  { icon: <FaTachometerAlt />, label: 'Dashboard', path: '/dashboard' },
  { icon: <FaVideo />,            label: 'Media Creator',   path: '/upload'    },
  { icon: <FaUsersCog />,         label: 'Account(s) Manager', path: '/accounts'  },
  { icon: <FaCalendarAlt />,      label: 'Upload Schedule', path: '/schedule'  },
  { icon: <FaCog />,              label: 'Settings',        path: '/settings'  }
];

const Sidebar = () => (
  <aside className="w-64 bg-white shadow-md p-6 flex flex-col justify-between">
    <div>
      <h1 className="text-2xl font-bold mb-8 text-blue-600">omniposter</h1>
      <nav className="space-y-4">
        {navItems.map(({ icon, label, path }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `flex items-center space-x-3 p-2 rounded hover:text-blue-600
               ${isActive ? 'bg-blue-50 text-blue-600' : 'text-gray-700'}`
            }
          >
            <span className="text-lg">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
    <div className="text-sm text-gray-500 mt-8">
      <a
        href="#"
        className="flex items-center space-x-1 text-blue-500 hover:underline"
      >
        <FaQuestionCircle />
        <span>Help Link</span>
      </a>
      <div className="mt-2">&copy; 2025</div>
    </div>
  </aside>
);

export default Sidebar;
