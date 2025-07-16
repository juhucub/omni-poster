import React, { useState } from 'react';
import { setGoals } from '../api/accounts.ts';

export const GoalForm: React.FC<{ accountId: number; onDone: () => void }> = ({
  accountId, onDone
}) => {
  const [views, setViews] = useState<number>();
  const [likes, setLikes] = useState<number>();
  const [followers, setFollowers] = useState<number>();

  const submit = async () => {
    await setGoals(accountId, { views, likes, followers });
    onDone();
  };

  return (
    <div className="p-4 bg-gray-50 rounded shadow space-y-2">
      <h4 className="font-semibold">Set Goals</h4>
      <div className="grid grid-cols-3 gap-2">
        <input type="number" placeholder="Views"      onChange={e=>setViews(+e.target.value)} className="input-field" />
        <input type="number" placeholder="Likes"      onChange={e=>setLikes(+e.target.value)}   className="input-field" />
        <input type="number" placeholder="Followers"  onChange={e=>setFollowers(+e.target.value)} className="input-field" />
      </div>
      <button onClick={submit} className="px-3 py-1 bg-green-500 text-white rounded">Save Goals</button>
      <button onClick={onDone} className="px-3 py-1 text-gray-600">Cancel</button>
    </div>
  );
};
