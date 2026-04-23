import React, { useEffect, useState } from 'react';

import apiClient from '../api/client';
import type { PublishJob, PublishedPost } from '../api/models';
import Sidebar from '../components/Sidebar';

const PublishHistoryPage: React.FC = () => {
  const [history, setHistory] = useState<{ jobs: PublishJob[]; posts: PublishedPost[] }>({ jobs: [], posts: [] });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await apiClient.get<{ jobs: PublishJob[]; posts: PublishedPost[] }>('/publish-history');
        setHistory(response.data);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load publish history.');
      }
    };
    void load();
  }, []);

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="mx-auto max-w-6xl rounded-3xl border border-white/10 bg-white/[0.04] p-6">
          <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">History</div>
          <h1 className="mt-2 text-4xl font-semibold">Publish history</h1>
          {error ? <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <div className="space-y-3">
              <h2 className="text-sm uppercase tracking-[0.3em] text-cyan-200/70">Jobs</h2>
              {history.jobs.map((job) => (
                <div key={job.id} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                  <div className="font-medium">#{job.id} · {job.status}</div>
                  <div className="mt-1 text-sm text-slate-400">{job.routing_platform}</div>
                </div>
              ))}
            </div>
            <div className="space-y-3">
              <h2 className="text-sm uppercase tracking-[0.3em] text-cyan-200/70">Posts</h2>
              {history.posts.map((post) => (
                <a key={post.id} href={post.external_url} target="_blank" rel="noreferrer" className="block rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                  <div className="font-medium">{post.external_url}</div>
                  <div className="mt-1 text-sm text-slate-400">{post.platform}</div>
                </a>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default PublishHistoryPage;
