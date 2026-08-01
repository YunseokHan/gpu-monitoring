import type { NodeStatus } from '../types'

const STATUS: Record<NodeStatus, { color: string; label: string }> = {
  online: { color: 'var(--good)', label: 'online' },
  stale: { color: 'var(--warning)', label: 'stale' },
  offline: { color: 'var(--critical)', label: 'offline' },
}

/** Status is always dot + word: colour never carries the meaning by itself. */
export function StatusDot({ status, detail }: { status: NodeStatus; detail?: string }) {
  const { color, label } = STATUS[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--ink-2)' }}>
      <span
        className="inline-block h-2 w-2 shrink-0 rounded-full"
        style={{ background: color }}
        aria-hidden
      />
      {label}
      {detail && <span style={{ color: 'var(--muted)' }}>· {detail}</span>}
    </span>
  )
}
