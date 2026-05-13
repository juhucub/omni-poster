import React, { useEffect, useState } from 'react';

import apiClient from '../api/client';
import type { SocialAccount } from '../api/models';
import StudioShell from '../components/studio/StudioShell';

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
    <StudioShell mainClassName="studio-detail-surface">
      <div className="mx-auto w-full max-w-5xl space-y-6">
        <div className="studio-page-hero">
          <div className="studio-page-kicker">Channels</div>
          <h1 className="mt-2">Connected destinations</h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-400">
            Manage release destinations used by Command Room routing and production publish drafts.
          </p>
        </div>
        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
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
      </div>
    </StudioShell>
  );
};

export default AccountManager;
