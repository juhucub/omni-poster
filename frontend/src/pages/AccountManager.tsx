import React, { useEffect, useState } from 'react';

import apiClient from '../api/client';
import type { SocialAccount } from '../api/models';
import Sidebar from '../components/Sidebar';

const AccountManager: React.FC = () => {
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await apiClient.get<{ items: SocialAccount[] }>('/social-accounts');
        setAccounts(response.data.items || []);
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load accounts.');
      }
    };

    void load();
  }, []);

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="mx-auto max-w-5xl rounded-3xl border border-white/10 bg-white/[0.04] p-6">
          <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Accounts</div>
          <h1 className="mt-2 text-4xl font-semibold">Connected destinations</h1>
          {error ? (
            <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </div>
          ) : null}
          <div className="mt-6 space-y-3">
            {accounts.map((account) => (
              <div key={account.id} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                <div className="font-medium">{account.channel_title}</div>
                <div className="mt-1 text-sm text-slate-400">
                  {account.platform} · {account.token_status}
                </div>
              </div>
            ))}
            {accounts.length === 0 ? (
              <div className="text-sm text-slate-400">No social accounts connected yet.</div>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  );
};

export default AccountManager;
