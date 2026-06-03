import React from 'react';

type Tone = 'neutral' | 'active' | 'ready' | 'warning' | 'failed' | 'info' | 'brand' | 'muted';

const toneClass = (tone: Tone) => `studio-tone-${tone}`;

export const StudioPageHeader: React.FC<{
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
}> = ({ eyebrow, title, description, actions, meta }) => (
  <section className="panel studio-page-header">
    <div className="studio-page-header-copy">
      {eyebrow && <span className="eyebrow studio-page-kicker">{eyebrow}</span>}
      <h1 className="hero-title">{title}</h1>
      {description && <p className="lede">{description}</p>}
      {meta && <div className="studio-page-header-meta">{meta}</div>}
    </div>
    {actions && <div className="studio-page-header-actions">{actions}</div>}
  </section>
);

export const StudioPanel: React.FC<{
  title?: React.ReactNode;
  description?: React.ReactNode;
  badge?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}> = ({ title, description, badge, children, className = '', id }) => (
  <section id={id} className={`panel studio-panel ${className}`.trim()}>
    {(title || description || badge) && (
      <div className="panel-h studio-panel-head">
        <div>
          {title && <h2>{title}</h2>}
          {description && <p>{description}</p>}
        </div>
        {badge}
      </div>
    )}
    {children}
  </section>
);

export const StudioCard: React.FC<{
  children: React.ReactNode;
  className?: string;
  tone?: Tone;
}> = ({ children, className = '', tone = 'neutral' }) => (
  <div className={`panel tight studio-card ${toneClass(tone)} ${className}`.trim()}>{children}</div>
);

export const StudioButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'warning' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}> = ({ variant = 'secondary', size = 'md', className = '', children, ...props }) => (
  <button className={`btn studio-button studio-button-${variant} ${size === 'sm' ? 'sm' : size === 'lg' ? 'lg' : ''} ${variant === 'primary' ? 'primary' : variant === 'ghost' ? 'ghost' : variant === 'warning' ? 'warn' : variant === 'danger' ? 'fail' : ''} ${className}`.trim()} type="button" {...props}>
    {children}
  </button>
);

export const StudioStatusBadge: React.FC<{
  children: React.ReactNode;
  tone?: Tone;
  pulse?: boolean;
  className?: string;
}> = ({ children, tone = 'neutral', pulse = false, className = '' }) => (
  <span className={`chip studio-status-badge ${tone === 'active' ? 'is-active' : tone === 'ready' ? 'is-ready' : tone === 'warning' ? 'is-warning' : tone === 'failed' ? 'is-failed' : tone === 'info' ? 'is-info' : tone === 'brand' ? 'is-brand' : 'plain'} ${toneClass(tone)} ${pulse ? 'pulse is-pulsing' : ''} ${className}`.trim()}>
    {children}
  </span>
);

export const StudioMetricCard: React.FC<{
  value: React.ReactNode;
  label: React.ReactNode;
  detail?: React.ReactNode;
  tone?: Tone;
}> = ({ value, label, detail, tone = 'neutral' }) => (
  <StudioCard tone={tone} className="studio-metric-card">
    <strong>{value}</strong>
    <span>{label}</span>
    {detail && <small>{detail}</small>}
  </StudioCard>
);

export const StudioEmptyState: React.FC<{
  title: React.ReactNode;
  description: React.ReactNode;
  action?: React.ReactNode;
}> = ({ title, description, action }) => (
  <div className="studio-state studio-empty-state">
    <strong>{title}</strong>
    <p>{description}</p>
    {action && <div className="studio-state-action">{action}</div>}
  </div>
);

export const StudioLoadingState: React.FC<{ label?: string }> = ({ label = 'Loading studio data...' }) => (
  <div className="studio-state studio-loading-state" role="status" aria-live="polite">
    <span className="studio-loading-dot" />
    {label}
  </div>
);

export const StudioErrorState: React.FC<{ message: React.ReactNode }> = ({ message }) => (
  <div className="studio-state studio-error-state" role="alert">
    {message}
  </div>
);

export const StudioTabs: React.FC<{
  tabs: Array<{ key: string; label: string; count?: number }>;
  activeKey: string;
  onChange: (key: string) => void;
  label: string;
}> = ({ tabs, activeKey, onChange, label }) => (
  <div className="libbar studio-tabs" role="tablist" aria-label={label}>
    <span className="libbar-label">Library</span>
    <div className="libbar-pills">
    {tabs.map((tab) => (
      <button
        key={tab.key}
        type="button"
        role="tab"
        aria-selected={activeKey === tab.key}
        className="lib-pill studio-tab"
        aria-pressed={activeKey === tab.key}
        onClick={() => onChange(tab.key)}
      >
        <span>{tab.label}</span>
        {typeof tab.count === 'number' && <em className="lib-n">{tab.count}</em>}
      </button>
    ))}
    </div>
  </div>
);

export const StudioDiagnosticsPanel: React.FC<{
  title?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}> = ({ title = 'Advanced diagnostics', children, defaultOpen = false }) => (
  <details className="drawer studio-diagnostics" open={defaultOpen}>
    <summary>{title}<StudioStatusBadge tone="active">Collapsed</StudioStatusBadge></summary>
    <div className="studio-diagnostics-body">{children}</div>
  </details>
);
