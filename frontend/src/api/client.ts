import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { generateSecureToken } from '../utils/security';

/**
 * Secure HTTP client with CSRF protection and JWT auth headers
 */
class APIClient {
  private readonly client: AxiosInstance;
  private csrfToken: string | null = null;
  private authToken: string | null = null;

  constructor(baseURL: string = process.env.REACT_APP_API_URL || '/api') {
    this.client = axios.create({
      baseURL,
      timeout: 30000,
      withCredentials: true,
      headers: { 'Content-Type': 'application/json' }
    });
    this.setupInterceptors();
  }

  /**
   * Retrieve stored JWT auth token
   */
  public getAuthToken(): string | null {
    return this.authToken;
  }

  /**
   * Store JWT auth token
   */
  public setAuthToken(token: string): void {
    this.authToken = token;
  }

  /**
   * Clear stored JWT auth token
   */
  public clearAuthToken(): void {
    this.authToken = null;
  }

  /**
   * Refresh CSRF token via API
   */
  public async refreshCSRFToken(): Promise<void> {
    const response = await this.client.get<{ csrfToken: string }>('/auth/csrf-token');
    this.csrfToken = response.data.csrfToken;
  }

  private setupInterceptors(): void {
    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        // Add JWT token
        if (this.authToken) {
          config.headers = config.headers || {};
          config.headers.Authorization = `Bearer ${this.authToken}`;
        }
        // Add CSRF token
        if (['post','put','patch','delete'].includes(config.method || '')) {
          if (this.csrfToken) {
            config.headers = config.headers || {};
            config.headers['X-CSRF-Token'] = this.csrfToken;
          }
        }
        // Add request ID
        config.headers = config.headers || {};
        config.headers['X-Request-ID'] = generateSecureToken(16);
        return config;
      },
      error => Promise.reject(error)
    );

    this.client.interceptors.response.use(
      (response: AxiosResponse) => {
        const newCsrf = response.headers['x-csrf-token'];
        if (newCsrf) this.csrfToken = newCsrf;
        return response;
      },
      async error => {
        const originalRequest = error.config;
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          this.clearAuthToken();
          this.csrfToken = null;
          window.dispatchEvent(new CustomEvent('auth:logout'));
          return Promise.reject(error);
        }
        if (error.response?.status === 403 && error.response.data?.error === 'CSRF_TOKEN_MISMATCH') {
          try {
            await this.refreshCSRFToken();
            return this.client.request(originalRequest);
          } catch {
            return Promise.reject(error);
          }
        }
        return Promise.reject(error);
      }
    );
  }

  /**
   * Expose Axios instance for direct use
   */
  public get instance(): AxiosInstance {
    return this.client;
  }
}

// Export singleton client
const API = new APIClient();
export default API;
export type { APIClient };
