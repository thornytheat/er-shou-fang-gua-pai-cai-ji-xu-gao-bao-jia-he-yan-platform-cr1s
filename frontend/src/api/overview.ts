import { http } from './client';
import type { Overview } from '../types/models';

export const overviewApi = {
  get: () => http.get<Overview>('/overview'),
};
