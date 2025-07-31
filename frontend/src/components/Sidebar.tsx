// File: src/components/Sidebar.jsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import {

  FaQuestionCircle
} from 'react-icons/fa';

import {
  Aperture,
  Clapperboard,
  Users,
  CalendarClock,
  Settings
} from 'lucide-react';

const navItems = [
  { icon: <Aperture />, label: 'Dashboard', path: '/dashboard' },
  { icon: <Clapperboard />,            label: 'Media Creator',   path: '/upload'    },
  { icon: <Users />,         label: 'Account(s) Manager', path: '/accounts'  },
  { icon: <CalendarClock />,      label: 'Upload Schedule', path: '/schedule'  },
  { icon: <Settings />,              label: 'Settings',        path: '/settings'  }
];

const Sidebar = () => (
  <aside className="bg-[#17183D] border-b border-gray-100 sticky p-6 flex flex-col justify-between">
    <div>
      <h1 className="text-2xl font-bold mb-8 text-white ">Omniposter</h1>
      <nav className="space-y-4">
        {navItems.map(({ icon, label, path }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `flex items-center space-x-3 p-2 rounded hover:border-1
               ${isActive ? 'bg-purple-600 text-white' : 'text-gray-200'}`
            }
          >
            <span className="text-lg">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
    <div className="text-sm text-purple-900 mt-8">
      <a
        href="#"
        className="flex items-center space-x-1 text-purple-500 hover:underline"
      >
        <FaQuestionCircle />
        <span>Help Link</span>
      </a>
      <div className="mt-2">&copy; 2025</div>
    </div>
  </aside>
);

export default Sidebar;
