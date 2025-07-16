// src/pages/AccountManagerPage.tsx
import React from 'react';
import { CreateAccount } from '../components/CreateAccount';
import { AccountList }   from '../components/AccountList';

const AccountManagerPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Account Manager</h1>
      <CreateAccount />
      <AccountList />
    </div>
  );
};

export default AccountManagerPage;
