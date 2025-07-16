import axios from 'axios';

export interface AccountOut {
  id: number;
  platform: string;
  name: string;
  profile_picture: string;
  stats: { followers: number; views: number; likes: number };
  status: string;
}

export interface GoalIn { followers?: number; views?: number; likes?: number; }

export const listAccounts = () => axios.get<AccountOut[]>('/accounts');
export const createAccount = (platform: string, code: string) =>
  axios.post<AccountOut>('/accounts', { platform, oauth_code: code });
export const deleteAccount = (id: number) => axios.delete(`/accounts/${id}`);
export const reconnectAccount = (id: number) => axios.patch(`/accounts/${id}/reconnect`);
export const setGoals = (id: number, goals: GoalIn) =>
  axios.post(`/accounts/${id}/goals`, goals);
