import { useCallback, useMemo, useState } from 'react'
import { ControlError, controlToken, setDummy } from './api'
import { NodeCard } from './components/NodeCard'
import { useStream } from './useStream'
import { gb } from './format'

/** Frames older than this mean the tunnel or the hub dropped out. */
const STALE_AFTER_S = 4

export default function App() {
  const { state, connected, staleness, transport } = useStream()
  const [pending, setPending] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const canControl = controlToken.length > 0

  const toggleDummy = useCallback(
    async (nodeId: string, gpuIndex: number | null, enabled: boolean) => {
      const key = `${nodeId}:${gpuIndex ?? 'all'}`
      setPending((prev) => new Set(prev).add(key))
      setError(null)
      try {
        await setDummy(nodeId, gpuIndex, enabled)
      } catch (err) {
        setError(err instanceof ControlError ? err.message : String(err))
      } finally {
        setPending((prev) => {
          const next = new Set(prev)
          next.delete(key)
          return next
        })
      }
    },
    [],
  )

  const totals = useMemo(() => {
    const gpus = state?.nodes.flatMap((node) => node.gpus) ?? []
    return {
      nodes: state?.nodes.length ?? 0,
      gpus: gpus.length,
      busy: gpus.filter((gpu) => gpu.processes.some((p) => !p.is_dummy)).length,
      dummy: gpus.filter((gpu) => gpu.dummy_active).length,
      free: gpus.filter((gpu) => gpu.processes.length === 0).length,
      usedMb: gpus.reduce((sum, gpu) => sum + gpu.mem_used_mb, 0),
      totalMb: gpus.reduce((sum, gpu) => sum + gpu.mem_total_mb, 0),
    }
  }, [state])

  const live = connected && staleness < STALE_AFTER_S

  return (
    <div className="mx-auto max-w-[1600px] px-3 py-3 sm:px-4 sm:py-4">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-semibold" style={{ color: 'var(--ink)' }}>
            GPU Cluster
          </h1>
          {!canControl && (
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide"
              style={{ background: 'var(--surface-2)', color: 'var(--muted)' }}
              title="Append ?k=<control token> to the URL to enable the dummy switches"
            >
              read-only
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--ink-2)' }}>
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: live ? 'var(--good)' : 'var(--warning)' }}
            aria-hidden
          />
          {live ? 'live' : connected ? 'waiting for data' : 'reconnecting'}
          <span
            className="tabular-nums"
            style={{ color: 'var(--muted)' }}
            title={transport === 'poll' ? 'polling once a second (the stream is buffered upstream)' : 'server-sent events'}
          >
            · {staleness < 1 ? 'now' : `${staleness.toFixed(0)}s ago`}
          </span>
        </div>
      </header>

      {state && (
        <div
          className="mb-3 flex flex-wrap gap-x-5 gap-y-1 rounded-lg px-3 py-2 text-[11px]"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--hairline)' }}
        >
          <Stat label="nodes" value={String(totals.nodes)} />
          <Stat label="GPUs" value={String(totals.gpus)} />
          <Stat label="in use" value={String(totals.busy)} />
          <Stat label="held by dummy" value={String(totals.dummy)} accent="var(--dummy)" />
          <Stat label="free" value={String(totals.free)} />
          <Stat label="VRAM" value={`${gb(totals.usedMb)} / ${gb(totals.totalMb)} GB`} />
        </div>
      )}

      {error && (
        <p
          className="mb-3 rounded px-3 py-2 text-[11px]"
          style={{
            background: 'color-mix(in oklab, var(--critical) 15%, var(--surface-2))',
            color: 'var(--ink)',
          }}
          role="alert"
        >
          {error}
        </p>
      )}

      {!state && (
        <p className="py-10 text-center text-sm" style={{ color: 'var(--muted)' }}>
          {connected ? 'Waiting for the first snapshot…' : 'Connecting to the hub…'}
        </p>
      )}

      {state && state.nodes.length === 0 && (
        <p className="py-10 text-center text-sm" style={{ color: 'var(--muted)' }}>
          No agents have reported yet.
        </p>
      )}

      <div className="space-y-3">
        {state?.nodes.map((node) => (
          <NodeCard
            key={node.node_id}
            node={node}
            canControl={canControl}
            pending={pending}
            onToggleDummy={(gpuIndex, enabled) => toggleDummy(node.node_id, gpuIndex, enabled)}
          />
        ))}
      </div>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="tabular-nums font-semibold" style={{ color: accent ?? 'var(--ink)' }}>
        {value}
      </span>
      <span style={{ color: 'var(--muted)' }}>{label}</span>
    </span>
  )
}
