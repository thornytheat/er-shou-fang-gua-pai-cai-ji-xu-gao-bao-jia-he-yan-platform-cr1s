export const PAGE_SIZE = 18;

export const NAV_ITEMS = [
  { to: '/listings', label: '挂牌池', no: '01', permission: 'listing:read' },
  { to: '/flags', label: '核验队列', no: '02', permission: 'flag:read' },
  { to: '/sources', label: '采集源与运行', no: '03', permission: 'source:read' },
];

export const DEMO_ACCOUNTS = [
  { email: 'admin@rentlens.io', label: '研究组长', who: '沈砚' },
  { email: 'analyst@rentlens.io', label: '数据专员', who: '许清' },
  { email: 'client@rentlens.io', label: '中介客户只读', who: '安家地产 · 王经理' },
];

export const SCENARIO_NOTES = [
  { k: '5', v: '采集平台', d: '聚合站 / 信息港 / 论坛 / 朋友圈 / 群公告' },
  { k: '240', v: '每天挂牌', d: '去重后 194 套在售' },
  { k: '32', v: '重复组', d: '同一套房在 2~3 个平台重复挂牌' },
  { k: '12', v: '价格工单', d: '7 虚高 / 3 虚低 / 2 待确认' },
];

export const SOURCE_HIGHLIGHTS = [
  '链家式聚合站：字段最规整，单价/总价/精确楼层齐全',
  '安居式信息港：楼层只给「中楼层(共18层)」，要补层号',
  '业主论坛：中文日期、没有联系方式字段，字段完整度低',
  '中介朋友圈存档：标题带口语词，单价常有小幅上调',
  '门店群公告：一行一条，日期只有 MM-DD，靠年度锚点补全',
];
