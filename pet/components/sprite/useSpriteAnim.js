// 动画矩阵：显式 (state × mood) → animationName 解析
// 语义与现状 CSS 保持一致：心情动画优先于状态动画；drag 映射到 idle。
// 值必须是 config.json animations 中存在的键；渲染器不做拼接/回退猜测，
// 缺失键由渲染器统一回退到 'idle'。
const MATRIX = {
  idle:   { '': 'idle',        happy: 'idle_happy',   annoyed: 'idle_annoyed',  dizzy: 'idle_dizzy',   purring: 'idle_purring' },
  walk:   { '': 'walk',        happy: 'walk_happy',   annoyed: 'walk',          dizzy: 'walk',         purring: 'walk' },
  drag:   { '': 'idle',        happy: 'idle_happy',   annoyed: 'idle_annoyed',  dizzy: 'idle_dizzy',   purring: 'idle_purring' },
  react:  { '': 'react',       happy: 'react',        annoyed: 'react',         dizzy: 'react',        purring: 'react' },
  think:  { '': 'think',       happy: 'idle_happy',   annoyed: 'idle_annoyed',  dizzy: 'idle_dizzy',   purring: 'idle_purring' },
  talk:   { '': 'talk',        happy: 'talk',         annoyed: 'talk',          dizzy: 'talk',         purring: 'talk' },
  sleep:  { '': 'sleep',       happy: 'idle_happy',   annoyed: 'idle_annoyed',  dizzy: 'idle_dizzy',   purring: 'idle_purring' },
  remind: { '': 'remind',      happy: 'remind',       annoyed: 'remind',        dizzy: 'remind',       purring: 'remind' },
}

// 渲染器唯一入口：任何 (state, mood) 组合都能得到确定性动画名（永不返回 undefined）
export function resolveAnimation(state, mood) {
  const row = MATRIX[state]
  if (!row) return 'idle'
  const moodKey = mood || ''
  return row[moodKey] ?? row[''] ?? 'idle'
}

export { MATRIX }