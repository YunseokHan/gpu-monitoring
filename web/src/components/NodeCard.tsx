import type { NodeView } from '../types'
import { ago, gb } from '../format'
import { GpuCard } from './GpuCard'
import { StatusDot } from './StatusDot'
import { Toggle } from './Toggle'

interface NodeCardProps {
  node: NodeView
  canControl: boolean
  pending: Set<string>
  onToggleDummy: (gpuIndex: number | null, enabled: boolean) => void
}

export function NodeCard({ node, canControl, pending, onToggleDummy }: NodeCardProps) {
  const allOn = node.gpus.length > 0 && node.gpus.every((gpu) => gpu.dummy_enabled)
  const usedMb = node.gpus.reduce((sum, gpu) => sum + gpu.mem_used_mb, 0)
  const totalMb = node.gpus.reduce((sum, gpu) => sum + gpu.mem_total_mb, 0)
  const idle = node.gpus.filter((gpu) => gpu.processes.length === 0).length
  const dimmed = node.status === 'offline'

  return (
    <section
      className="rounded-xl p-3 sm:p-4"
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--hairline)',
        opacity: dimmed ? 0.55 : 1,
      }}
    >
      <header className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className="rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
            style={{ background: 'var(--surface-1)', color: 'var(--ink-2)' }}
            title="node number"
          >
            #{node.node_index}
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold" style={{ color: 'var(--ink)' }}>
              {node.node_id}
            </h2>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px]" style={{ color: 'var(--muted)' }}>
              {node.hostname !== node.node_id && <span>{node.hostname}</span>}
              <span>{node.gpus.length} GPU</span>
              {node.driver_version && <span>driver {node.driver_version}</span>}
              {node.cuda_version && <span>CUDA {node.cuda_version}</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right text-[10px] tabular-nums" style={{ color: 'var(--muted)' }}>
            <div>
              {gb(usedMb)} / {gb(totalMb)} GB used
            </div>
            <div>{idle} idle</div>
          </div>
          <StatusDot status={node.status} detail={node.status === 'online' ? undefined : ago(node.age_s)} />
          <label className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--ink-2)' }}>
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
          className="mb-3 rounded px-2 py-1 text-[11px]"
          style={{ background: 'color-mix(in oklab, var(--warning) 18%, var(--surface-1))', color: 'var(--ink-2)' }}
        >
          ⚠ {node.error}
        </p>
      )}

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {node.gpus.map((gpu) => (
          <GpuCard
            key={gpu.index}
            gpu={gpu}
            canControl={canControl && !dimmed}
            busy={pending.has(`${node.node_id}:${gpu.index}`)}
            onToggleDummy={(enabled) => onToggleDummy(gpu.index, enabled)}
          />
        ))}
      </div>
    </section>
  )
}
