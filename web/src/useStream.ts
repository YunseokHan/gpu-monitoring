import { useEffect, useRef, useState } from 'react'
import type { ClusterState } from './types'

const MAX_BACKOFF_MS = 15_000
const POLL_INTERVAL_MS = 1000
/**
 * If SSE has produced nothing in this long, something between us and the hub is holding
 * the stream and we switch to polling. Cloudflare's edge does exactly this: it buffers
 * ~128 KiB of a streamed response before flushing, which turns a 1 Hz stream into a
 * burst whose period grows with the frame size. Plain responses pass straight through,
 * so polling always works.
 *
 * The watchdog is re-armed on every frame, not just before the first one. A stream that
 * delivers a burst and then silently stalls keeps its connection open, so `onerror`
 * never fires -- without a running watchdog the dashboard would freeze for good.
 *
 * Keep this comfortably above the edge's flush period: a full buffer at the current
 * frame size lands every ~5 s, and treating that as a stall would send every viewer to
 * polling the moment the cluster grew.
 */
const SSE_STALL_MS = 12_000

export type Transport = 'sse' | 'poll' | 'connecting'

export interface StreamState {
  state: ClusterState | null
  connected: boolean
  /** Seconds since the last update actually arrived -- the honest "is this live?" signal. */
  staleness: number
  transport: Transport
}

/** ?transport=sse|poll pins the transport; otherwise SSE is tried first. */
const forced = new URLSearchParams(window.location.search).get('transport')

export function useStream(): StreamState {
  const [state, setState] = useState<ClusterState | null>(null)
  const [connected, setConnected] = useState(false)
  const [staleness, setStaleness] = useState(0)
  const [transport, setTransport] = useState<Transport>('connecting')
  const lastUpdate = useRef<number>(Date.now())

  useEffect(() => {
    let cancelled = false
    let polling = false
    let source: EventSource | null = null
    let sseRetry: number | undefined
    let watchdog: number | undefined
    let pollTimer: number | undefined
    let backoff = 1000

    const accept = (payload: ClusterState) => {
      lastUpdate.current = Date.now()
      setConnected(true)
      setState(payload)
    }

    // ---------------------------------------------------------------- polling

    const poll = async () => {
      if (cancelled) return
      try {
        const response = await fetch('/api/v1/state', { cache: 'no-store' })
        if (!response.ok) throw new Error(String(response.status))
        accept(await response.json())
      } catch {
        setConnected(false)
      }
      if (!cancelled) pollTimer = window.setTimeout(poll, POLL_INTERVAL_MS)
    }

    const startPolling = () => {
      if (cancelled || polling) return
      polling = true
      setTransport('poll')
      source?.close()
      source = null
      window.clearTimeout(sseRetry)
      window.clearTimeout(watchdog)
      void poll()
    }

    // -------------------------------------------------------------------- SSE

    /** Give up on SSE if nothing arrives before this fires. Re-armed by every frame. */
    const armWatchdog = () => {
      window.clearTimeout(watchdog)
      watchdog = window.setTimeout(startPolling, SSE_STALL_MS)
    }

    const connectSse = () => {
      if (cancelled || polling) return
      source = new EventSource('/api/v1/stream')
      armWatchdog()

      source.addEventListener('state', (event) => {
        armWatchdog()
        backoff = 1000
        setTransport('sse')
        try {
          accept(JSON.parse((event as MessageEvent).data))
        } catch {
          /* a truncated frame is not worth tearing the connection down for */
        }
      })

      source.onerror = () => {
        setConnected(false)
        source?.close()
        source = null
        if (cancelled || polling) return
        // EventSource retries on its own, but not after every failure mode; drive it
        // explicitly so a tunnel restart cannot leave the page permanently dead. The
        // watchdog keeps running across reconnects, so a stream that only ever fails
        // ends up on polling rather than retrying forever.
        sseRetry = window.setTimeout(connectSse, backoff)
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
      }
    }

    if (forced === 'poll') startPolling()
    else connectSse()

    const ticker = window.setInterval(
      () => setStaleness((Date.now() - lastUpdate.current) / 1000),
      500,
    )

    return () => {
      cancelled = true
      source?.close()
      window.clearTimeout(sseRetry)
      window.clearTimeout(watchdog)
      window.clearTimeout(pollTimer)
      window.clearInterval(ticker)
    }
  }, [])

  return { state, connected, staleness, transport }
}
