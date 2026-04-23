import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import apiClient from '../api/client';
import type { SocialAccount } from '../api/models';
import Sidebar from '../components/Sidebar';

const AccountManager: React.FC = () => {
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  const oauthStatus = searchParams.get('youtube_oauth');
  const oauthMessage = searchParams.get('message');

  const loadAccounts = async () => {
    try {
      const response = await apiClient.get<{ items: SocialAccount[] }>('/social-accounts');
      setAccounts(response.data.items);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load social accounts.');
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    if (!oauthStatus) {
      return;
    }

    if (oauthStatus === 'success') {
      setInfo('YouTube account linked successfully.');
      loadAccounts();
    } else if (oauthStatus === 'error') {
      setError(oauthMessage || 'YouTube linking failed.');
    }

    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('youtube_oauth');
    nextParams.delete('message');
    nextParams.delete('account_id');
    setSearchParams(nextParams, { replace: true });
  }, [oauthMessage, oauthStatus, searchParams, setSearchParams]);

  const reconnectRequired = useMemo(
    () => accounts.filter((account) => account.status === 'reconnect_required').length,
    [accounts]
  );

  const connectYoutube = async () => {
    try {
      setBusy(true);
      const response = await apiClient.post<{ authorization_url: string }>('/social-accounts/youtube/connect/start');
      window.location.href = response.data.authorization_url;
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start YouTube linking.');
      setBusy(false);
    }
  };

  const refreshAccount = async (accountId: number) => {
    try {
      await apiClient.post(`/social-accounts/${accountId}/refresh`);
      setInfo('Account token refreshed.');
      await loadAccounts();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to refresh account.');
    }
  };

  const disconnectAccount = async (accountId: number) => {
    try {
      await apiClient.delete(`/social-accounts/${accountId}`);
      await loadAccounts();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to disconnect account.');
    }
  };

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="max-w-5xl mx-auto space-y-8">
          <header>
            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Publishing destinations</div>
            <h1 className="mt-2 text-4xl font-semibold">Publishing Accounts</h1>
            <p className="mt-3 text-slate-400">
              Link the destination channel before you route, approve, and publish a project.
            </p>
            {reconnectRequired > 0 && (
              <p className="mt-3 text-amber-300">
                {reconnectRequired} linked account needs to reconnect before it can publish again.
              </p>
            )}
          </header>

          {info && <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-emerald-200">{info}</div>}
          {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-rose-200">{error}</div>}

          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <button
              onClick={connectYoutube}
              disabled={busy}
              className="rounded-2xl bg-cyan-300 px-5 py-4 font-medium text-slate-950 disabled:opacity-60"
            >
              {busy ? 'Redirecting to Google...' : 'Connect YouTube Account'}
            </button>
          </section>

          <section className="grid gap-4">
            {accounts.length === 0 && (
              <div className="rounded-3xl border border-dashed border-white/15 bg-white/[0.04] p-8 text-slate-400">
                No linked accounts yet.
              </div>
            )}
            {accounts.map((account) => (
              <div key={account.id} className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <div className="flex items-center justify-between gap-6">
                  <div>
                    <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{account.status}</div>
                    <h2 className="mt-2 text-2xl font-semibold">{account.channel_title}</h2>
                    <p className="mt-2 text-sm text-slate-400">{account.channel_id}</p>
                    <p className="mt-1 text-sm text-slate-400">
                      {account.platform} · {account.account_type} · token {account.token_status}
                    </p>
                    <p className="mt-1 text-sm text-slate-400">
                      Capabilities: {account.capabilities.join(', ')} {account.routing_eligible ? '· eligible' : '· not eligible'}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    {account.status === 'reconnect_required' && (
                      <button
                        onClick={() => refreshAccount(account.id)}
                        className="rounded-2xl bg-amber-300 px-4 py-3 text-sm font-medium text-slate-950"
                      >
                        Refresh Token
                      </button>
                    )}
                    <button
                      onClick={() => disconnectAccount(account.id)}
                      className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10"
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </section>
        </div>
      </main>
    </div>
  );
};

export default AccountManager;
