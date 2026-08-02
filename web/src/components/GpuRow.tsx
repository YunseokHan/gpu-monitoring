import type { GpuSnapshot } from '../types'
import { gb, pct } from '../format'
import { Toggle } from './Toggle'

/**
 * One GPU as a single compact row, in the spirit of nvidia-smi's device table:
 * identity on the left, the two meters stacked in the middle with their numbers to the
 * left of each bar, then temperature and power as their own columns.
 *
 * The grid is shared by every row (see GPU_GRID) so the columns line up down the whole
 * node, which is the entire point of laying it out this way.
 */
// The labelled columns are fixed; the bar takes whatever the card has left. Its base
// size is the 3rem minimum and it grows toward 22rem only while there is free space, so
// it fills a half-width card exactly and still cannot stretch to a full-window smear --
// a bar that grows without limit reads as "full" whatever its value.
//
// Do NOT add a trailing 1fr spacer here: the second meter row is auto-placed, and a
// spare cell in row 1 swallows its first child.
export const GPU_GRID =
  'grid-cols-[6rem_2.25rem_6rem_minmax(3rem,22rem)_2.75rem_5rem_2rem]'

interface GpuRowProps {
  gpu: GpuSnapshot
  canControl: boolean
  busy: boolean
  onToggleDummy: (enabled: boolean) => void
}

function shortName(name: string): string {
  return name.replace(/^NVIDIA\s+/i, '')
}

export function GpuRow({ gpu, canControl, busy, onToggleDummy }: GpuRowProps) {
  const memPercent = pct(gpu.mem_used_mb, gpu.mem_total_mb)
  const others = gpu.processes.filter((p) => !p.is_dummy)
  const yielded = gpu.dummy_enabled && !gpu.dummy_active && others.length > 0

  return (
    <div
      className={`grid ${GPU_GRID} items-center gap-x-2 py-1.5 pl-2 pr-1`}
      style={{
        borderTop: '1px solid var(--grid)',
        borderLeft: gpu.dummy_active ? '2px solid var(--dummy)' : '2px solid transparent',
      }}
    >
      {/* identity, spanning both meter rows */}
      <div className="row-span-2 min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-xs font-semibold tabular-nums" style={{ color: 'var(--ink)' }}>
            GPU {gpu.index}
          </span>
          {gpu.dummy_active && (
            <span
              className="rounded px-1 text-[9px] font-semibold uppercase"
              style={{
                background: 'color-mix(in oklab, var(--dummy) 22%, var(--surface-1))',
                color: 'var(--dummy)',
              }}
              title={`dummy holding this GPU (${gpu.dummy_backend ?? 'unknown'} backend)`}
            >
              dummy
            </span>
          )}
        </div>
        <div className="truncate text-[10px] leading-3" style={{ color: 'var(--muted)' }}>
          {gpu.dummy_error ? (
            <span style={{ color: 'var(--critical)' }} title={gpu.dummy_error}>
              dummy failed
            </span>
          ) : yielded ? (
            'dummy on · yielded'
          ) : (
            shortName(gpu.name)
          )}
        </div>
      </div>

      <MeterCells
        label="VRAM"
        value={`${gb(gpu.mem_used_mb)} / ${gb(gpu.mem_total_mb)}`}
        percent={memPercent}
        hue="--vram"
        title={`${gpu.mem_used_mb} MiB of ${gpu.mem_total_mb} MiB in use`}
      />

      {/* temperature and power, spanning both meter rows */}
      <div
        className="row-span-2 text-right text-[11px] tabular-nums"
        style={{ color: 'var(--ink-2)' }}
      >
        {gpu.temp_c == null ? '—' : `${gpu.temp_c}°C`}
      </div>
      <div
        className="row-span-2 text-right text-[11px] tabular-nums"
        style={{ color: 'var(--ink-2)' }}
      >
        {gpu.power_w == null
          ? '—'
          : `${Math.round(gpu.power_w)}${gpu.power_limit_w == null ? '' : ` / ${Math.round(gpu.power_limit_w)}`} W`}
      </div>

      <div className="row-span-2 flex justify-end">
        <Toggle
          checked={gpu.dummy_enabled}
          disabled={!canControl}
          busy={busy}
          label={`dummy on GPU ${gpu.index}`}
          onChange={onToggleDummy}
        />
      </div>

      <MeterCells
        label="Util"
        value={gpu.util_gpu == null ? '—' : `${gpu.util_gpu}%`}
        percent={gpu.util_gpu ?? 0}
        hue="--util"
        title="GPU utilization over the last sampling window"
      />
    </div>
  )
}

/**
 * The three cells of one meter: name, number, bar. Emitted as a fragment so they land
 * directly in the parent grid and stay aligned with every other row.
 */
function MeterCells({
  label,
  value,
  percent,
  hue,
  title,
}: {
  label: string
  value: string
  percent: number
  hue: string
  title: string
}) {
  const clamped = Math.max(0, Math.min(100, percent))
  return (
    <>
      <span className="text-[10px]" style={{ color: 'var(--muted)' }}>
        {label}
      </span>
      <span
        className="text-right text-[11px] tabular-nums"
        style={{ color: 'var(--ink-2)' }}
        title={title}
      >
        {value}
      </span>
      <div
        className="h-1.5 w-full overflow-hidden rounded-sm"
        style={{ background: `color-mix(in oklab, var(${hue}) 20%, var(--surface-2))` }}
        role="meter"
        aria-label={label}
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        title={title}
      >
        <div
          className="h-full rounded-sm transition-[width] duration-500 ease-out"
          style={{ width: `${clamped}%`, background: `var(${hue})` }}
        />
      </div>
    </>
  )
}
