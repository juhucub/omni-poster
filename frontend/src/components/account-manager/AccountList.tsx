import React, { useEffect, useState } from 'react';
import { listAccounts, deleteAccount, reconnectAccount, AccountOut } from '../../api/accounts.ts';
import { AccountCard } from './AccountCard.tsx';
import { GoalForm } from './GoalForm.tsx';

export const AccountList: React.FC = () => {
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [selected, select] = useState<number|null>(null);

  const reload = async () => {
    const resp = await listAccounts();
    setAccounts(resp.data);
  };

  useEffect(() => { reload(); }, []);

  return (
    <div className="space-y-4">
      {accounts.map(acct => (
        <AccountCard
          key={acct.id}
          acct={acct}
          onDelete={() => { deleteAccount(acct.id).then(reload); }}
          onReconnect={() => { reconnectAccount(acct.id).then(reload); }}
          onSetGoals={() => select(acct.id)}
        />
      ))}
      {selected && <GoalForm accountId={selected} onDone={() => { select(null); reload(); }} />}
    </div>
  );
};
