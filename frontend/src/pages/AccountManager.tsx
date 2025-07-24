// src/pages/AccountManagerPage.tsx
import React from 'react';
import { CreateAccount } from '../components/account-manager/CreateAccount.tsx';
import { AccountList }   from '../components/account-manager/AccountList.tsx';

const AccountManager: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Account Manager</h1>
      <CreateAccount />
      <AccountList />
    </div>
  );
};

export default AccountManager;
