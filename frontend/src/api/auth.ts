import { http } from './client';
import type { UserInfo } from '../types/models';

export const authApi = {
  login: (email: string, password: string) =>
    http.post<{ access_token: string; token_type: string; expires_in: number; user: UserInfo }>(
      '/auth/login',
      { email, password },
    ),
  me: () => http.get<{ user: UserInfo }>('/auth/me'),
};
