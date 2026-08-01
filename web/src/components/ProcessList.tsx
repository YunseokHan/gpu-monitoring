import type { ProcInfo } from '../types'
import { gb } from '../format'

export function ProcessList({ processes }: { processes: ProcInfo[] }) {
  if (processes.length === 0) {
    return (
      <p className="text-[11px] italic" style={{ color: 'var(--muted)' }}>
        no processes
      </p>
    )
  }

  return (
    <ul className="space-y-1">
      {processes.map((proc) => (
        <li key={`${proc.pid}-${proc.kind}`} className="text-[11px] leading-4">
          <div className="flex items-baseline justify-between gap-2">
            <span className="flex min-w-0 items-baseline gap-1.5">
              {proc.is_dummy && (
                <span
                  className="shrink-0 rounded px-1 py-px text-[9px] font-semibold uppercase tracking-wide"
                  style={{
                    background: 'color-mix(in oklab, var(--dummy) 22%, var(--surface-2))',
                    color: 'var(--dummy)',
                  }}
                >
                  dummy
                </span>
              )}
              <span className="truncate font-medium" style={{ color: 'var(--ink)' }}>
                {proc.name}
              </span>
              <span className="shrink-0 tabular-nums" style={{ color: 'var(--muted)' }}>
                {proc.user || '?'} · {proc.pid}
              </span>
            </span>
            <span className="shrink-0 tabular-nums" style={{ color: 'var(--ink-2)' }}>
              {proc.used_mem_mb == null ? '—' : `${gb(proc.used_mem_mb)} GB`}
            </span>
          </div>
          {proc.cmdline && (
            <div className="truncate" style={{ color: 'var(--muted)' }} title={proc.cmdline}>
              {proc.cmdline}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
