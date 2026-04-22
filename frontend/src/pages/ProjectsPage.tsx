import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, RefreshCw } from 'lucide-react';

import apiClient from '../api/client';
import type { Project } from '../api/models';
import Sidebar from '../components/Sidebar';

const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get<{ items: Project[] }>('/projects');
      setProjects(response.data.items);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load projects.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const createProject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }

    try {
      setSubmitting(true);
      const response = await apiClient.post<Project>('/projects', {
        name: name.trim(),
        target_platform: 'youtube',
        automation_mode: 'assisted',
        allowed_platforms: ['youtube'],
      });
      navigate(`/projects/${response.data.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create project.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="max-w-6xl mx-auto space-y-8">
          <section className="rounded-[28px] border border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.18),_transparent_35%),linear-gradient(135deg,#111827,#0f172a)] p-8">
            <div className="flex items-start justify-between gap-6">
              <div>
                <div className="text-sm uppercase tracking-[0.3em] text-cyan-200/70">Project-first workflow</div>
                <h2 className="mt-3 text-4xl font-semibold">Create Shorts from editable dialogue scripts</h2>
                <p className="mt-3 max-w-2xl text-slate-300">
                  Projects hold the script, background video, preview state, metadata, publishing destination, and post history.
                </p>
              </div>
              <button
                onClick={loadProjects}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm hover:bg-white/10"
              >
                <RefreshCw size={16} />
                Refresh
              </button>
            </div>

            <form onSubmit={createProject} className="mt-8 flex flex-col gap-3 sm:flex-row">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Name your next Shorts project"
                className="flex-1 rounded-2xl border border-white/10 bg-slate-950/60 px-5 py-4 text-slate-100 placeholder:text-slate-500 focus:border-cyan-300 focus:outline-none"
              />
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-5 py-4 font-medium text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <Plus size={18} />
                {submitting ? 'Creating...' : 'New Project'}
              </button>
            </form>
            {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}
          </section>

          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {loading && (
              <div className="rounded-3xl border border-white/10 bg-white/5 p-6 text-slate-300">Loading projects...</div>
            )}
            {!loading && projects.length === 0 && (
              <div className="rounded-3xl border border-dashed border-white/15 bg-white/5 p-8 text-slate-300">
                No projects yet. Start with a background video and dialogue script.
              </div>
            )}
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => navigate(`/projects/${project.id}`)}
                className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-left transition hover:border-cyan-300/40 hover:bg-white/[0.06]"
              >
                <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{project.status}</div>
                <h3 className="mt-4 text-2xl font-semibold">{project.name}</h3>
                <p className="mt-2 text-sm text-slate-400">Platform: {project.target_platform}</p>
                <p className="mt-1 text-sm text-slate-400">Style: {project.background_style}</p>
                <p className="mt-1 text-sm text-slate-400">Automation: {project.automation_mode}</p>
                <p className="mt-4 text-sm text-slate-300">
                  {project.current_script
                    ? `${project.current_script.characters.length} characters in current script`
                    : 'No script saved yet'}
                </p>
                {project.latest_review && (
                  <p className="mt-2 text-sm text-amber-200">Review: {project.latest_review.status}</p>
                )}
              </button>
            ))}
          </section>
        </div>
      </main>
    </div>
  );
};

export default ProjectsPage;
