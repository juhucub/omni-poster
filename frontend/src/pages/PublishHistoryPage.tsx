import React, { useEffect, useState } from 'react';

import apiClient from '../api/client';
import type { PublishJob, PublishedPost } from '../api/models';
import Sidebar from '../components/Sidebar';

const PublishHistoryPage: React.FC = () => {
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [posts, setPosts] = useState<PublishedPost[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await apiClient.get<{ jobs: PublishJob[]; posts: PublishedPost[] }>('/publish-history');
        setJobs(response.data.jobs);
        setPosts(response.data.posts);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load publish history.');
      }
    };
    loadHistory();
  }, []);

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="max-w-6xl mx-auto space-y-8">
          <header>
            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Status truth</div>
            <h1 className="mt-2 text-4xl font-semibold">Publish History</h1>
            <p className="mt-3 text-slate-400">Queued, scheduled, failed, and published records all live here.</p>
          </header>

          {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-rose-200">{error}</div>}

          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <h2 className="text-xl font-semibold">Publish Jobs</h2>
            <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-white/5 text-slate-300">
                  <tr>
                    <th className="px-4 py-3">Job</th>
                    <th className="px-4 py-3">Project</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Scheduled</th>
                    <th className="px-4 py-3">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id} className="border-t border-white/10">
                      <td className="px-4 py-3">#{job.id}</td>
                      <td className="px-4 py-3">{job.project_id}</td>
                      <td className="px-4 py-3">{job.status}</td>
                      <td className="px-4 py-3">{job.scheduled_for || '-'}</td>
                      <td className="px-4 py-3 text-rose-200">{job.last_error || '-'}</td>
                    </tr>
                  ))}
                  {jobs.length === 0 && (
                    <tr>
                      <td className="px-4 py-6 text-slate-400" colSpan={5}>
                        No publish jobs yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <h2 className="text-xl font-semibold">Published Posts</h2>
            <div className="mt-4 space-y-3">
              {posts.map((post) => (
                <a
                  key={post.id}
                  href={post.external_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-2xl border border-white/10 bg-slate-950/40 p-4 transition hover:border-cyan-300/40"
                >
                  <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{post.platform}</div>
                  <div className="mt-2 font-medium">{post.external_url}</div>
                  <div className="mt-1 text-sm text-slate-400">Published at {post.published_at}</div>
                </a>
              ))}
              {posts.length === 0 && <div className="text-slate-400">No posts have been published yet.</div>}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};

export default PublishHistoryPage;
