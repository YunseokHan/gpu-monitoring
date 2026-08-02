import type { NodeView } from '../types'
import { ago, gb } from '../format'
import { GPU_GRID, GpuRow } from './GpuRow'
import { ProcessTable } from './ProcessTable'
import { StatusDot } from './StatusDot'
import { Toggle } from './Toggle'

interface NodeCardProps {
  node: NodeView
  canControl: boolean
  pending: Set<string>
  onToggleDummy: (gpuIndex: number | null, enabled: boolean) => void
  /** Inside a cluster card the surrounding chrome is already there; stay flat. */
  nested?: boolean
}

export function NodeCard({ node, canControl, pending, onToggleDummy, nested }: NodeCardProps) {
  const allOn = node.gpus.length > 0 && node.gpus.every((gpu) => gpu.dummy_enabled)
  const usedMb = node.gpus.reduce((sum, gpu) => sum + gpu.mem_used_mb, 0)
  const totalMb = node.gpus.reduce((sum, gpu) => sum + gpu.mem_total_mb, 0)
  const idle = node.gpus.filter((gpu) => gpu.processes.length === 0).length
  const dimmed = node.status === 'offline'

  return (
    <section
      className="overflow-hidden rounded-lg"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--hairline)',
        opacity: dimmed ? 0.55 : 1,
      }}
    >
      <header
        className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-2.5 py-1.5"
        style={{ background: nested ? 'transparent' : 'var(--surface-2)' }}
      >
        <div className="flex min-w-0 items-baseline gap-2">
          <span
            className="rounded px-1 text-[10px] font-semibold tabular-nums"
            style={{ background: 'var(--surface-2)', color: 'var(--ink-2)' }}
            title="node number"
          >
            #{node.node_index}
          </span>
          <h3 className="truncate text-[13px] font-semibold" style={{ color: 'var(--ink)' }}>
            {node.node_id}
          </h3>
          <span className="truncate text-[10px]" style={{ color: 'var(--muted)' }}>
            {node.gpus.length}× {node.gpus[0]?.name.replace(/^NVIDIA\s+/i, '') ?? '?'}
            {node.driver_version && (
              <span className="hidden sm:inline"> · driver {node.driver_version}</span>
            )}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] tabular-nums" style={{ color: 'var(--muted)' }}>
            {gb(usedMb)} / {gb(totalMb)} GB · {idle} idle
          </span>
          <StatusDot
            status={node.status}
            detail={node.status === 'online' ? undefined : ago(node.age_s)}
          />
          <label className="flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--ink-2)' }}>
            <span>all dummy</span>
            <Toggle
              checked={allOn}
              disabled={!canControl || dimmed}
              busy={pending.has(`${node.node_id}:all`)}
              label={`dummy on every GPU of ${node.node_id}`}
              onChange={(next) => onToggleDummy(null, next)}
            />
          </label>
        </div>
      </header>

      {node.error && (
        <p
          className="px-2.5 py-1 text-[11px]"
          style={{
            background: 'color-mix(in oklab, var(--warning) 18%, var(--surface-1))',
            color: 'var(--ink-2)',
          }}
        >
          ⚠ {node.error}
        </p>
      )}

      {/* The device table has a minimum width to stay aligned; on a narrow embed this
          block scrolls sideways on its own rather than squashing the columns. */}
      <div className="overflow-x-auto">
        <div className="min-w-[31rem]">
          <div
            className={`grid ${GPU_GRID} gap-x-2 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide`}
            style={{ color: 'var(--muted)' }}
          >
            <span>Device</span>
            <span className="col-span-3">Memory / Utilization</span>
            <span className="text-right">Temp</span>
            <span className="text-right">Power</span>
            <span />
          </div>

          {node.gpus.map((gpu) => (
            <GpuRow
              key={gpu.index}
              gpu={gpu}
              canControl={canControl && !dimmed}
              busy={pending.has(`${node.node_id}:${gpu.index}`)}
              onToggleDummy={(enabled) => onToggleDummy(gpu.index, enabled)}
            />
          ))}

          <ProcessTable gpus={node.gpus} />
        </div>
      </div>
    </section>
  )
}
