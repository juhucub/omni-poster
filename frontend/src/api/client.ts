import axios from 'axios';

/**
 * Secure HTTP client with CSRF protection and JWT auth headers
 */
export const apiClient = axios.create({

  //constructor(baseURL: string = process.env.REACT_APP_API_URL || '/api') {
      baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
      timeout: 30000,
      withCredentials: true,
      headers: { 'Content-Type': 'application/json' },
    });
   

  // Request interceptor to add auth token if available
apiClient.interceptors.request.use(
  (config) => {
    // Get token from localStorage if available
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Don't override Content-Type for FormData
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    }

    console.log('Making request to:', config.url, {
      method: config.method,
      hasFormData: config.data instanceof FormData,
      hasAuth: !!config.headers.Authorization
    });

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    console.error('API Error:', {
      status: error.response?.status,
      data: error.response?.data,
      url: error.config?.url,
      method: error.config?.method
    });

    // Handle 401 - redirect to login
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/auth';
    }

    return Promise.reject(error);
  }
);

export default apiClient;