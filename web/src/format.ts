export function gb(mib: number): string {
  const value = mib / 1024
  return value >= 100 ? value.toFixed(0) : value.toFixed(1)
}

export function pct(used: number, total: number): number {
  return total > 0 ? Math.min(100, (used / total) * 100) : 0
}

export function ago(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  return `${Math.round(seconds / 3600)}h ago`
}
