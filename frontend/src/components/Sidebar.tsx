import React from 'react';
import { NavLink } from 'react-router-dom';
import { History, Link as LinkIcon, LayoutDashboard } from 'lucide-react';

const navItems = [
  { icon: <LayoutDashboard size={18} />, label: 'Projects', path: '/projects' },
  { icon: <LinkIcon size={18} />, label: 'Accounts', path: '/accounts' },
  { icon: <History size={18} />, label: 'Publish History', path: '/history' },
];

const Sidebar: React.FC = () => (
  <aside className="w-full max-w-60 bg-[#11162b] text-white p-6 border-r border-white/10">
    <div className="mb-8">
      <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Omni-poster</div>
      <h1 className="mt-2 text-2xl font-semibold">Review-Driven Studio</h1>
    </div>

    <nav className="space-y-2">
      {navItems.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-4 py-3 transition ${
              isActive ? 'bg-cyan-400 text-slate-950' : 'text-slate-200 hover:bg-white/10'
            }`
          }
        >
          {item.icon}
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  </aside>
);

export default Sidebar;
