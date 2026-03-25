import { API_URL } from './api';

export interface User {
  name: string;
  role: string;
  department?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_name: string;
  role: string;
  is_new_user?: boolean;
}

export const login = async (name: string, birthDate: string): Promise<LoginResponse> => {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name, birth_date: birthDate }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Login failed');
  }

  return response.json();
};

export const ssoLogin = async (code: string, redirectUri: string): Promise<LoginResponse> => {
  const response = await fetch(`${API_URL}/api/auth/sso-login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'SSO Login failed');
  }

  return response.json();
};

export const logout = () => {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_name');
    window.location.href = '/login';
  }
};
