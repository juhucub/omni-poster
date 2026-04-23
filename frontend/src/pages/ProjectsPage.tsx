import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import apiClient from '../api/client';
import type { Project } from '../api/models';
import Sidebar from '../components/Sidebar';

const ProjectsPage: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('New Project');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadProjects = async () => {
    try {
      const response = await apiClient.get<{ items: Project[] }>('/projects');
      setProjects(response.data.items || []);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load projects.');
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const createProject = async () => {
    try {
      setBusy(true);
      await apiClient.post('/projects', { name, target_platform: 'youtube' });
      setName('New Project');
      await loadProjects();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create project.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="mx-auto max-w-6xl">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Projects</div>
              <h1 className="mt-2 text-4xl font-semibold">Create and review renders</h1>
            </div>
          </div>

          <div className="mt-6 rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <div className="flex flex-wrap gap-3">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="flex-1 rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                placeholder="Project name"
              />
              <button onClick={createProject} disabled={busy} className="rounded-2xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-60">
                {busy ? 'Creating...' : 'Create Project'}
              </button>
            </div>
            {error ? <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((project) => (
              <Link key={project.id} to={`/projects/${project.id}`} className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 hover:border-cyan-300/40">
                <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{project.status}</div>
                <div className="mt-2 text-xl font-semibold">{project.name}</div>
                <div className="mt-2 text-sm text-slate-400">{project.target_platform}</div>
              </Link>
            ))}
            {projects.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-white/15 bg-slate-950/30 p-6 text-sm text-slate-400">
                No projects yet. Create one to begin the render workflow.
              </div>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  );
};

export default ProjectsPage;
