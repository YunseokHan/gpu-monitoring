import type { GpuSnapshot } from '../types'
import { gb } from '../format'

/**
 * Every process on the node in one table at the bottom, the way nvidia-smi prints them
 * once below the device table rather than repeating them per card.
 */
export function ProcessTable({ gpus }: { gpus: GpuSnapshot[] }) {
  const rows = gpus.flatMap((gpu) => gpu.processes.map((proc) => ({ gpu: gpu.index, proc })))

  return (
    <div className="pt-1">
      <div
        className="grid grid-cols-[2.5rem_4.5rem_5.5rem_minmax(8rem,1fr)_5rem] gap-x-2 px-2 py-1 text-[9px] font-semibold uppercase tracking-wide"
        style={{ color: 'var(--muted)', borderTop: '1px solid var(--grid)' }}
      >
        <span>GPU</span>
        <span>PID</span>
        <span>User</span>
        <span>Process</span>
        <span className="text-right">Memory</span>
      </div>

      {rows.length === 0 ? (
        <p className="px-2 py-1.5 text-[11px] italic" style={{ color: 'var(--muted)' }}>
          No running processes found
        </p>
      ) : (
        rows.map(({ gpu, proc }) => (
          <div
            key={`${gpu}-${proc.pid}-${proc.kind}`}
            className="grid grid-cols-[2.5rem_4.5rem_5.5rem_minmax(8rem,1fr)_5rem] items-baseline gap-x-2 px-2 py-0.5 text-[11px] leading-4"
          >
            <span className="tabular-nums" style={{ color: 'var(--ink-2)' }}>
              {gpu}
            </span>
            <span className="tabular-nums" style={{ color: 'var(--muted)' }}>
              {proc.pid}
            </span>
            <span className="truncate" style={{ color: 'var(--muted)' }}>
              {proc.user || '?'}
            </span>
            <span className="min-w-0 truncate" title={proc.cmdline || proc.name}>
              <span
                className="font-medium"
                style={{ color: proc.is_dummy ? 'var(--dummy)' : 'var(--ink)' }}
              >
                {proc.name}
              </span>
              {proc.cmdline && (
                <span style={{ color: 'var(--muted)' }}> — {proc.cmdline}</span>
              )}
            </span>
            <span className="text-right tabular-nums" style={{ color: 'var(--ink-2)' }}>
              {proc.used_mem_mb == null ? '—' : `${gb(proc.used_mem_mb)} GB`}
            </span>
          </div>
        ))
      )}
    </div>
  )
}
