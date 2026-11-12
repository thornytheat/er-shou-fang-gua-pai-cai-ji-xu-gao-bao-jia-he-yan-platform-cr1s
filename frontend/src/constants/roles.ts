/** 角色权限（与 backend/src/constants/roles.py 一一对应）。 */
import type { Role } from '../types/models';

export const ROLE_LABELS: Record<string, string> = {
  admin: '研究组长',
  analyst: '数据专员',
  client: '中介客户（只读）',
};

export const ROLE_DUTIES: Record<string, string> = {
  admin: '维护采集源与阈值、复核价格工单、导出行情周报、查看审计',
  analyst: '跑采集、复核工单、修正挂牌单价',
  client: '只读行情与核验进度，看不到原始联系方式',
};

export const PERMISSIONS: Record<string, string[]> = {
  admin: [
    'listing:read',
    'listing:write',
    'source:read',
    'source:write',
    'ingest:read',
    'ingest:run',
    'cluster:read',
    'cluster:recompute',
    'flag:read',
    'flag:review',
    'export:read',
    'audit:read',
    'contact:read',
  ],
  analyst: [
    'listing:read',
    'listing:write',
    'source:read',
    'ingest:read',
    'ingest:run',
    'cluster:read',
    'cluster:recompute',
    'flag:read',
    'flag:review',
    'contact:read',
  ],
  client: ['listing:read', 'cluster:read', 'flag:read'],
};

export function can(role: Role | undefined | null, permission: string): boolean {
  if (!role) return false;
  return (PERMISSIONS[role] || []).includes(permission);
}
