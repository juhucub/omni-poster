import React from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Boxes, Film, History, Link as LinkIcon, LayoutDashboard, Mic2 } from 'lucide-react';

import type { Project } from '../../api/models';
import { useAuth } from '../../context/AuthContext';
import '../command-room/commandRoom.css';
import './studio.css';

export type StudioSyncState = 'local' | 'paused' | 'active';

const titleCase = (value: string | null | undefined) =>
  String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());

const getStoredSyncState = (isAuthenticated: boolean): StudioSyncState => {
  if (!isAuthenticated) {
    return 'local';
  }
  if (typeof window === 'undefined') {
    return 'paused';
  }
  return window.localStorage.getItem('omniposter.studioSync') === 'active' ? 'active' : 'paused';
};

const navItems = [
  { icon: LayoutDashboard, label: 'Command Room', href: '/', match: (pathname: string, hash: string) => pathname === '/' && (!hash || hash === '#command-room') },
  { icon: Film, label: 'Productions', href: '/projects', match: (pathname: string, hash: string) => pathname.startsWith('/projects') || hash === '#active-productions' },
  { icon: Boxes, label: 'Content Formats', href: '/#start-production', match: (pathname: string, hash: string) => pathname === '/' && hash === '#start-production' },
  { icon: Mic2, label: 'Voice Lab', href: '/voice-lab', match: (pathname: string) => pathname.startsWith('/voice-lab') },
  { icon: LayoutDashboard, label: 'Scene Library', href: '/#scene-library', match: (pathname: string, hash: string) => pathname === '/' && hash === '#scene-library' },
  { icon: LinkIcon, label: 'Channels', href: '/accounts', match: (pathname: string, hash: string) => pathname.startsWith('/accounts') || hash === '#channels' },
  { icon: History, label: 'Release History', href: '/history', match: (pathname: string) => pathname.startsWith('/history') },
];

export const StudioSidebar: React.FC<{
  currentProject?: Project | null;
  syncState?: StudioSyncState;
}> = ({ currentProject, syncState = 'local' }) => {
  const location = useLocation();

  return (
    <aside className="op-sidebar" role="navigation" aria-label="Main navigation">
      <Link to="/" className="op-brand-card" aria-label="Open Command Room">
        <div className="op-brand-logo">
          <div className="op-brand-mark">OP</div>
          <span className="op-brand-name">OmniPoster</span>
        </div>
        <div className="op-brand-tagline">Local-first production studio</div>
      </Link>
      <nav className="op-nav" aria-label="Studio navigation">
        <div className="op-nav-section-label">Studio</div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = item.match(location.pathname, location.hash);
          const content = (
            <>
              <span className="op-nav-glyph" aria-hidden="true">
                <Icon size={14} />
              </span>
              <span>{item.label}</span>
            </>
          );
          return item.href.includes('#') ? (
            <a key={item.label} href={item.href} className={`op-nav-item ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}>
              {content}
            </a>
          ) : (
            <NavLink key={item.label} to={item.href} className={() => `op-nav-item ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}>
              {content}
            </NavLink>
          );
        })}
      </nav>
      <div className="op-sidebar-bottom">
        <div className="op-current-production-mini">
          <div className="op-current-prod-label">Current Production</div>
          <div className="op-current-prod-title">{currentProject?.name || 'No production loaded'}</div>
          <div className="op-current-prod-step" style={{ color: syncState === 'paused' ? 'var(--paused)' : syncState === 'active' ? 'var(--success)' : 'var(--warning)' }}>
            {syncState === 'paused' ? 'Sync Paused' : currentProject?.status ? titleCase(currentProject.status) : syncState === 'active' ? 'Sync Active' : 'Local Workspace'}
          </div>
        </div>
      </div>
    </aside>
  );
};

export const StudioShell: React.FC<{
  children: React.ReactNode;
  currentProject?: Project | null;
  syncState?: StudioSyncState;
  mainClassName?: string;
}> = ({ children, currentProject = null, syncState, mainClassName = '' }) => {
  const { isAuthenticated } = useAuth();
  const resolvedSyncState = syncState || getStoredSyncState(isAuthenticated);

  return (
    <div className="op-shell">
      <StudioSidebar currentProject={currentProject} syncState={resolvedSyncState} />
      <main className={`op-main ${mainClassName}`.trim()} role="main">
        {children}
      </main>
    </div>
  );
};

export default StudioShell;
