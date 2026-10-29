import type { QuotaView } from '../types'
import { ago, pct } from '../format'
import { StatusDot } from './StatusDot'

/** Hours with one decimal below 100, whole hours above, and thousands separators. */
function hours(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: value < 100 ? 1 : 0 })
}

/** Whole days from today to the last day of the period, counting that day itself. */
function daysLeft(periodEnd: string): number | null {
  const end = Date.parse(`${periodEnd}T23:59:59`)
  if (Number.isNaN(end)) return null
  return Math.max(0, Math.ceil((end - Date.now()) / 86_400_000))
}

/**
 * A Slurm site we can only see through its accounting service: no device table, just
 * how much of the allocation the group has used, and by whom.
 *
 * The figures are the site's own, which update about once a day, so the card says when
 * they are from instead of pretending to be live.
 */
export function QuotaCard({ quota }: { quota: QuotaView }) {
  // Everything is shown in both node-hours (what the contract is written in) and
  // GPU-hours (what people think in), converted from the site's seconds.
  const perNode = quota.unit === 'node' ? quota.gpus_per_node : 1
  const nodeH = (s: number) => s / 3600 / (quota.unit === 'node' ? 1 : quota.gpus_per_node)
  const gpuH = (s: number) => (s / 3600) * perNode

  const used = quota.used_s
  const left = Math.max(0, quota.contract_s - used)
  const usedPct = pct(used, quota.contract_s)
  const remaining = daysLeft(quota.period_end)
  const users = [...quota.users].sort((a, b) => b.used_s - a.used_s)
  const dimmed = quota.status === 'offline'

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

      {quota.error && (
        <p
          className="px-2.5 py-1 text-[11px]"
          style={{
            background: 'color-mix(in oklab, var(--warning) 18%, var(--surface-1))',
            color: 'var(--ink-2)',
          }}
        >
          ⚠ {quota.error}
        </p>
      )}

      <div className="space-y-2 px-2.5 py-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
          <span className="text-[13px] tabular-nums" style={{ color: 'var(--ink)' }}>
            <span className="font-semibold">{hours(gpuH(left))}</span>
            <span style={{ color: 'var(--ink-2)' }}> GPU·h left</span>
            <span className="text-[11px]" style={{ color: 'var(--muted)' }}>
              {' '}
              ({hours(nodeH(left))} node·h)
            </span>
          </span>
          <span className="text-[11px] tabular-nums" style={{ color: 'var(--ink-2)' }}>
            used {hours(gpuH(used))} / {hours(gpuH(quota.contract_s))} GPU·h ·{' '}
            {usedPct.toFixed(usedPct < 10 ? 1 : 0)}%
          </span>
        </div>

        <div
          className="h-2 overflow-hidden rounded-full"
          style={{ background: 'var(--grid)' }}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(usedPct)}
          aria-label={`${quota.cluster} quota used`}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${usedPct}%`,
              background: usedPct >= 90 ? 'var(--critical)' : usedPct >= 75 ? 'var(--warning)' : 'var(--util)',
            }}
          />
        </div>

        <table className="w-full text-[11px] tabular-nums">
          <thead>
            <tr className="text-[9px] font-semibold uppercase tracking-wide" style={{ color: 'var(--muted)' }}>
              <th className="py-0.5 text-left font-semibold">User</th>
              <th className="py-0.5 text-right font-semibold">GPU·h</th>
              <th className="py-0.5 text-right font-semibold">node·h</th>
              <th className="py-0.5 text-right font-semibold">Share</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="py-1" style={{ color: 'var(--muted)' }}>
                  No usage recorded yet.
                </td>
              </tr>
            )}
            {users.map((user) => (
              <tr key={user.user} style={{ borderTop: '1px solid var(--hairline)' }}>
                <td className="py-0.5" style={{ color: 'var(--ink)' }}>
                  {user.user}
                </td>
                <td className="py-0.5 text-right" style={{ color: 'var(--ink)' }}>
                  {hours(gpuH(user.used_s))}
                </td>
                <td className="py-0.5 text-right" style={{ color: 'var(--ink-2)' }}>
                  {hours(nodeH(user.used_s))}
                </td>
                <td className="py-0.5 text-right" style={{ color: 'var(--ink-2)' }}>
                  {used > 0 ? `${((user.used_s / used) * 100).toFixed(0)}%` : '–'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="text-[10px]" style={{ color: 'var(--muted)' }}>
          {quota.source || 'site accounting'}
          {quota.source_ts ? `, read ${ago(Date.now() / 1000 - quota.source_ts)}` : ''}
          {' · the site counts usage through the previous day, so today’s jobs show up tomorrow'}
        </p>
      </div>
    </section>
  )
}
