import type { QuotaView } from '../types'
import { ago, pct } from '../format'
import { StatusDot } from './StatusDot'

/** One decimal below 100, whole numbers above, with thousands separators. */
function num(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: value < 100 ? 1 : 0 })
}

/** Whole days from today to the last day of the period, counting that day itself. */
function daysLeft(periodEnd: string): number | null {
  const end = Date.parse(`${periodEnd}T23:59:59`)
  if (Number.isNaN(end)) return null
  return Math.max(0, Math.ceil((end - Date.now()) / 86_400_000))
}

/**
 * A Slurm site we can only see through its accounting: no device table, just how much
 * of the contract the group has used, and by whom.
 *
 * The contract is kept in the site's own unit (ISAM's SRU-Time seconds), shown as is so
 * it can be checked against `isam`, and in GPU-hours next to it because that is the
 * figure people can reason about. ISAM bills a job the day after it ends, so what has
 * run since -- estimated from Slurm by the collector -- is shown on top, marked as such.
 */
export function QuotaCard({ quota }: { quota: QuotaView }) {
  const perUnitGpuS =
    (quota.node_s_per_unit || 1) * (quota.unit === 'node' ? quota.gpus_per_node : 1)
  const gpuH = (s: number) => (s * perUnitGpuS) / 3600
  const nodeH = (s: number) => gpuH(s) / Math.max(1, quota.gpus_per_node)

  const used = quota.used_s
  const pending = quota.pending_s ?? 0
  const total = quota.contract_s
  const left = Math.max(0, total - used - pending)
  const usedPct = pct(used, total)
  const pendingPct = Math.min(100 - usedPct, pct(pending, total))
  const remaining = daysLeft(quota.period_end)
  const users = [...quota.users].sort(
    (a, b) => b.used_s + (b.pending_s ?? 0) - (a.used_s + (a.pending_s ?? 0)),
  )
  const anyRunning = users.some((u) => (u.running_gpus ?? 0) > 0)
  const dimmed = quota.status === 'offline'
  const fill = usedPct + pendingPct >= 90 ? 'var(--critical)' : usedPct + pendingPct >= 75 ? 'var(--warning)' : 'var(--util)'

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
        style={{ background: 'var(--surface-2)' }}
      >
        <div className="flex min-w-0 items-baseline gap-2">
          <h3 className="truncate text-[13px] font-semibold" style={{ color: 'var(--ink)' }}>
            {quota.label || quota.cluster}
          </h3>
          <span className="truncate text-[10px]" style={{ color: 'var(--muted)' }}>
            Slurm quota · {quota.account}
            {quota.gpus_per_node > 1 && ` · ${quota.gpus_per_node} GPU/node`}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {quota.period_start && (
            <span className="text-[10px] tabular-nums" style={{ color: 'var(--muted)' }}>
              {quota.period_start} – {quota.period_end}
              {remaining !== null && ` · ${remaining}d left`}
            </span>
          )}
          <StatusDot
            status={quota.status}
            detail={quota.status === 'online' ? undefined : ago(quota.age_s)}
          />
        </div>
      </header>

      {[quota.error, quota.pending_error].filter(Boolean).map((message) => (
        <p
          key={message}
          className="px-2.5 py-1 text-[11px]"
          style={{
            background: 'color-mix(in oklab, var(--warning) 18%, var(--surface-1))',
            color: 'var(--ink-2)',
          }}
        >
          ⚠ {message}
        </p>
      ))}

      <div className="space-y-2 px-2.5 py-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
          <span className="text-[13px] tabular-nums" style={{ color: 'var(--ink)' }}>
            <span className="font-semibold">≈ {num(gpuH(left))}</span>
            <span style={{ color: 'var(--ink-2)' }}> GPU·h left</span>
            <span className="text-[11px]" style={{ color: 'var(--muted)' }}>
              {' '}
              ({num(nodeH(left))} node·h)
            </span>
          </span>
          <span className="text-[11px] tabular-nums" style={{ color: 'var(--ink-2)' }}>
            {(usedPct + pendingPct).toFixed(usedPct + pendingPct < 10 ? 1 : 0)}% used
          </span>
        </div>

        <div
          className="flex h-2 overflow-hidden rounded-full"
          style={{ background: 'var(--grid)' }}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(usedPct + pendingPct)}
          aria-label={`${quota.label || quota.cluster} quota used`}
        >
          <div className="h-full" style={{ width: `${usedPct}%`, background: fill }} />
          <div
            className="h-full"
            style={{ width: `${pendingPct}%`, background: fill, opacity: 0.45 }}
            title="run since ISAM last billed (estimated)"
          />
        </div>

        {/* The site's figure first, exactly as `isam` prints it, then the same in GPU-hours. */}
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px] tabular-nums">
          <dt style={{ color: 'var(--muted)' }}>SRU-Time</dt>
          <dd style={{ color: 'var(--ink)' }}>
            <span className="font-semibold">{used.toLocaleString('en-US')} s</span>
            {pending > 0 && (
              <span style={{ color: 'var(--ink-2)' }}> + ~{Math.round(pending).toLocaleString('en-US')} s today</span>
            )}
            <span style={{ color: 'var(--muted)' }}> / {total.toLocaleString('en-US')} s</span>
          </dd>
          <dt style={{ color: 'var(--muted)' }}>GPU·h</dt>
          <dd style={{ color: 'var(--ink)' }}>
            <span className="font-semibold">{num(gpuH(used))}</span>
            {pending > 0 && <span style={{ color: 'var(--ink-2)' }}> + ~{num(gpuH(pending))} today</span>}
            <span style={{ color: 'var(--muted)' }}> / {num(gpuH(total))} GPU·h</span>
          </dd>
        </dl>

        <table className="w-full text-[11px] tabular-nums">
          <thead>
            <tr className="text-[9px] font-semibold uppercase tracking-wide" style={{ color: 'var(--muted)' }}>
              <th className="py-0.5 text-left font-semibold">User</th>
              <th className="py-0.5 text-right font-semibold">SRU-Time s</th>
              <th className="py-0.5 text-right font-semibold">GPU·h</th>
              <th className="py-0.5 text-right font-semibold">+ today</th>
              {anyRunning && <th className="py-0.5 text-right font-semibold">Now</th>}
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr>
                <td colSpan={5} className="py-1" style={{ color: 'var(--muted)' }}>
                  No usage recorded yet.
                </td>
              </tr>
            )}
            {users.map((user) => (
              <tr key={user.user} style={{ borderTop: '1px solid var(--hairline)' }}>
                <td className="py-0.5" style={{ color: 'var(--ink)' }}>
                  {user.user}
                </td>
                <td className="py-0.5 text-right" style={{ color: 'var(--ink-2)' }}>
                  {user.used_s.toLocaleString('en-US')}
                </td>
                <td className="py-0.5 text-right" style={{ color: 'var(--ink)' }}>
                  {num(gpuH(user.used_s))}
                </td>
                <td className="py-0.5 text-right" style={{ color: 'var(--ink-2)' }}>
                  {user.pending_s ? `~${num(gpuH(user.pending_s))}` : '–'}
                </td>
                {anyRunning && (
                  <td className="py-0.5 text-right" style={{ color: 'var(--ink-2)' }}>
                    {user.running_gpus ? `${user.running_gpus} GPU` : '–'}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        <p className="text-[10px] leading-snug" style={{ color: 'var(--muted)' }}>
          SRU-Time is {quota.source || 'the site'}’s billed figure
          {quota.source_ts ? ` (read ${ago(Date.now() / 1000 - quota.source_ts)})` : ''}. ISAM adds a
          job only the day after it ends, so jobs that ended today and running jobs show
          up there tomorrow; “today” estimates them from Slurm. 1 SRU-Time s ={' '}
          {num(perUnitGpuS)} GPU-s.
        </p>
      </div>
    </section>
  )
}
