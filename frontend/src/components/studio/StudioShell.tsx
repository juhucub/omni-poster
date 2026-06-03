import React from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Boxes, Film, History, Images, Link as LinkIcon, LayoutDashboard, Mic2, UserRound } from 'lucide-react';

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
  { icon: UserRound, label: 'Characters', href: '/characters', match: (pathname: string) => pathname.startsWith('/characters') },
  { icon: Mic2, label: 'Voice Lab', href: '/voice-lab', match: (pathname: string) => pathname.startsWith('/voice-lab') },
  { icon: Images, label: 'Generated Media', href: '/generated-media', match: (pathname: string) => pathname.startsWith('/generated-media') },
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
    <aside className="sidebar op-sidebar" role="navigation" aria-label="Main navigation">
      <Link to="/" className="brand op-brand-card" aria-label="Open Command Room">
        <span className="glyph" />
        <span>
          <b>OmniPoster</b>
          <small>Production Studio</small>
        </span>
      </Link>
      <nav className="nav op-nav" aria-label="Studio navigation">
        <span className="nav-label op-nav-section-label">Production workflow</span>
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = item.match(location.pathname, location.hash);
          const content = (
            <>
              <span className="ico op-nav-glyph" aria-hidden="true">
                <Icon size={14} />
              </span>
              <span>{item.label}</span>
            </>
          );
          return item.href.includes('#') ? (
            <a key={item.label} href={item.href} className={`op-nav-item ${active ? 'active' : ''}`} aria-label={item.label} title={item.label} aria-current={active ? 'page' : undefined}>
              {content}
            </a>
          ) : (
            <NavLink key={item.label} to={item.href} className={() => `op-nav-item ${active ? 'active' : ''}`} aria-label={item.label} title={item.label} aria-current={active ? 'page' : undefined}>
              {content}
            </NavLink>
          );
        })}
      </nav>
      <div className="sidebar-foot op-sidebar-bottom">
        <div className="op-current-production-mini">
          <b>Current Production</b>
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
  topbarRuntimeChips?: React.ReactNode;
  topbarActions?: React.ReactNode;
}> = ({ children, currentProject = null, syncState, mainClassName = '', topbarRuntimeChips, topbarActions }) => {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const resolvedSyncState = syncState || getStoredSyncState(isAuthenticated);
  const crumb = location.pathname.startsWith('/projects/')
    ? 'Production Builder'
    : location.pathname.startsWith('/generated-media')
      ? 'Generated Media'
      : location.pathname === '/'
        ? 'Command Room'
        : titleCase(location.pathname.replace(/^\/+/, '') || 'Studio');

  return (
    <div className="shell op-shell">
      <StudioSidebar currentProject={currentProject} syncState={resolvedSyncState} />
      <main className={`main op-main ${mainClassName}`.trim()} role="main">
        <div className="content">
          <div className="topbar">
            <div className="crumbs">
              <span className="runtime"><span className="pulse" /> Local runtime</span>
              <span className="sep">·</span>
              <span>OmniPoster</span>
              <span className="sep">/</span>
              <b>{crumb}</b>
              {topbarRuntimeChips}
            </div>
            <div className="bar-actions">
              {topbarActions || (
                <>
                  <span className={`chip ${resolvedSyncState === 'active' ? 'is-ready' : resolvedSyncState === 'paused' ? 'is-warning' : 'is-info'}`}>
                    {resolvedSyncState === 'active' ? 'Sync active' : resolvedSyncState === 'paused' ? 'Sync paused' : 'Local workspace'}
                  </span>
                  {currentProject?.name && <span className="chip is-brand plain">{currentProject.name}</span>}
                </>
              )}
            </div>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
};

export default StudioShell;
