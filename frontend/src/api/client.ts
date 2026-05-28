import axios from 'axios';

const getApiBaseUrl = () => {
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL.replace(/\/+$/, '');
  }

  return '';
};

export const apiBaseUrl = getApiBaseUrl();

const apiClient = axios.create({
  baseURL: apiBaseUrl,
  withCredentials: true,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error)
);

export default apiClient;
