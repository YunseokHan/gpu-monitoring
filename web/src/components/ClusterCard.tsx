import type { NodeView } from '../types'
import { gb } from '../format'
import { NodeCard } from './NodeCard'

interface ClusterCardProps {
  name: string
  nodes: NodeView[]
  canControl: boolean
  pending: Set<string>
  onToggleDummy: (nodeId: string, gpuIndex: number | null, enabled: boolean) => void
}

/** Nodes that reported the same cluster name, drawn inside one outer card. */
export function ClusterCard({ name, nodes, canControl, pending, onToggleDummy }: ClusterCardProps) {
  const gpus = nodes.flatMap((node) => node.gpus)
  const usedMb = gpus.reduce((sum, gpu) => sum + gpu.mem_used_mb, 0)
  const totalMb = gpus.reduce((sum, gpu) => sum + gpu.mem_total_mb, 0)
  const idle = gpus.filter((gpu) => gpu.processes.length === 0).length
  const offline = nodes.filter((node) => node.status !== 'online').length

  return (
    <section
      className="rounded-xl p-2"
      style={{ background: 'var(--surface-2)', border: '1px solid var(--hairline)' }}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-1 pb-2 pt-1">
        <div className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>
            {name}
          </h2>
          <span className="text-[10px]" style={{ color: 'var(--muted)' }}>
            cluster · {nodes.length} nodes · {gpus.length} GPUs
          </span>
        </div>
        <span className="text-[10px] tabular-nums" style={{ color: 'var(--muted)' }}>
          {gb(usedMb)} / {gb(totalMb)} GB · {idle} idle
          {offline > 0 && ` · ${offline} not reporting`}
        </span>
      </header>

      <div className="space-y-2">
        {nodes.map((node) => (
          <NodeCard
            key={node.node_id}
            node={node}
            canControl={canControl}
            pending={pending}
            nested
            onToggleDummy={(gpuIndex, enabled) => onToggleDummy(node.node_id, gpuIndex, enabled)}
          />
        ))}
      </div>
    </section>
  )
}
