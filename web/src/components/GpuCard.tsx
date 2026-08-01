import type { GpuSnapshot } from '../types'
import { gb, pct } from '../format'
import { Meter } from './Meter'
import { ProcessList } from './ProcessList'
import { Toggle } from './Toggle'

interface GpuCardProps {
  gpu: GpuSnapshot
  canControl: boolean
  busy: boolean
  onToggleDummy: (enabled: boolean) => void
}

/** Short model name: "NVIDIA A100-SXM4-80GB" -> "A100-SXM4-80GB". */
function shortName(name: string): string {
  return name.replace(/^NVIDIA\s+/i, '')
}

export function GpuCard({ gpu, canControl, busy, onToggleDummy }: GpuCardProps) {
  const others = gpu.processes.filter((p) => !p.is_dummy)
  const memPercent = pct(gpu.mem_used_mb, gpu.mem_total_mb)

  // Three states worth telling apart: actually holding the card, switched on but
  // standing aside because someone real is using it, and simply off.
  const dummyState = gpu.dummy_active
    ? 'holding'
    : gpu.dummy_enabled
      ? others.length > 0
        ? 'yielded'
        : 'starting'
      : 'off'

  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--hairline)',
        borderLeft: gpu.dummy_active ? '3px solid var(--dummy)' : '1px solid var(--hairline)',
      }}
    >
      <div className="mb-2.5 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[13px] font-semibold tabular-nums" style={{ color: 'var(--ink)' }}>
              GPU {gpu.index}
            </span>
            <span className="truncate text-[11px]" style={{ color: 'var(--muted)' }}>
              {shortName(gpu.name)}
            </span>
          </div>
          <DummyState state={dummyState} backend={gpu.dummy_backend} error={gpu.dummy_error} />
        </div>
        <Toggle
          checked={gpu.dummy_enabled}
          disabled={!canControl}
          busy={busy}
          label={`dummy on GPU ${gpu.index}`}
          onChange={onToggleDummy}
        />
      </div>

      <div className="space-y-2">
        <Meter
          label="Util"
          percent={gpu.util_gpu ?? 0}
          valueText={gpu.util_gpu == null ? '—' : `${gpu.util_gpu}%`}
          hue="--util"
          title="GPU utilization over the last sampling window"
        />
        <Meter
          label="VRAM"
          percent={memPercent}
          valueText={`${gb(gpu.mem_used_mb)} / ${gb(gpu.mem_total_mb)} GB`}
          hue="--vram"
          title={`${gpu.mem_used_mb} MiB of ${gpu.mem_total_mb} MiB in use`}
        />
      </div>

      <div
        className="mt-2 flex gap-3 text-[10px] tabular-nums"
        style={{ color: 'var(--muted)' }}
      >
        {gpu.temp_c != null && <span>{gpu.temp_c}°C</span>}
        {gpu.power_w != null && (
          <span>
            {Math.round(gpu.power_w)}
            {gpu.power_limit_w != null && ` / ${Math.round(gpu.power_limit_w)}`} W
          </span>
        )}
      </div>

      <div className="mt-2 border-t pt-2" style={{ borderColor: 'var(--grid)' }}>
        <ProcessList processes={gpu.processes} />
      </div>
    </div>
  )
}

const DUMMY_STATE_TEXT: Record<string, { text: string; color: string }> = {
  holding: { text: 'dummy holding this GPU', color: 'var(--dummy)' },
  yielded: { text: 'dummy on · yielded to a real job', color: 'var(--muted)' },
  starting: { text: 'dummy on · starting', color: 'var(--muted)' },
  off: { text: '', color: 'var(--muted)' },
}

function DummyState({
  state,
  backend,
  error,
}: {
  state: string
  backend: string | null
  error: string | null
}) {
  // A worker that could not start at all is the one thing here worth interrupting for --
  // on a node nobody can SSH into, this line is the whole diagnosis.
  if (error) {
    return (
      <div className="truncate text-[10px] leading-4" style={{ color: 'var(--critical)' }} title={error}>
        dummy failed: {error}
      </div>
    )
  }
  const entry = DUMMY_STATE_TEXT[state]
  if (!entry.text) return <div className="h-4" />
  return (
    <div className="truncate text-[10px] leading-4" style={{ color: entry.color }}>
      {entry.text}
      {state === 'holding' && backend && (
        <span style={{ color: 'var(--muted)' }}> · {backend}</span>
      )}
    </div>
  )
}
