import React from 'react';
import { AccountOut } from '../../api/accounts';

interface Props {
  acct: AccountOut;
  onDelete: () => void;
  onReconnect: () => void;
  onSetGoals: () => void;
}

export const AccountCard: React.FC<Props> = ({
  acct, onDelete, onReconnect, onSetGoals
}) => (
  <div className="p-4 bg-white rounded shadow flex items-center space-x-4">
    <img src={acct.profile_picture} alt="" className="w-16 h-16 rounded-full" />
    <div className="flex-1">
      <h3 className="font-bold">{acct.name} <small>({acct.platform})</small></h3>
      <p>Followers: {acct.stats.followers}  Views: {acct.stats.views}  Likes: {acct.stats.likes}</p>
      <span className={`px-2 py-1 rounded text-sm ${
          acct.status === 'authorized' ? 'bg-green-200' :
          acct.status === 'token_expired' ? 'bg-red-200' : 'bg-yellow-200'
        }`}>
        {acct.status.replace('_',' ')}
      </span>
    </div>
    <div className="space-y-2">
      <button onClick={onReconnect} className="block text-blue-600 hover:underline">Reconnect</button>
      <button onClick={onSetGoals}    className="block text-indigo-600 hover:underline">Set Goals</button>
      <button onClick={onDelete}      className="block text-red-600 hover:underline">Delete</button>
    </div>
  </div>
);
