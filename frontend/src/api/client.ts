import axios from 'axios';

const API = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  withCredentials: true,           // sends HTTP-only cookies
  headers: { 'Content-Type': 'application/json' },
});

export default API;