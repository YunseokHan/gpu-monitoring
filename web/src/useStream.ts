import { useEffect, useRef, useState } from 'react'
import type { ClusterState } from './types'

const MAX_BACKOFF_MS = 15_000
const POLL_INTERVAL_MS = 1000
/**
 * If SSE has produced nothing in this long, something between us and the hub is holding
 * the stream and we switch to polling. Cloudflare's edge does exactly this: it buffers
 * ~128 KiB of a streamed response before flushing, which turns a 1 Hz stream into a
 * burst every ~30 s. Plain responses pass straight through, so polling always works.
 */
const SSE_PROBATION_MS = 5000

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
    let sawFrame = false
    let source: EventSource | null = null
    let sseRetry: number | undefined
    let probation: number | undefined
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
      window.clearTimeout(probation)
      void poll()
    }

    // -------------------------------------------------------------------- SSE

    const connectSse = () => {
      if (cancelled || polling) return
      source = new EventSource('/api/v1/stream')

      window.clearTimeout(probation)
      probation = window.setTimeout(() => {
        if (!sawFrame) startPolling()
      }, SSE_PROBATION_MS)

      source.addEventListener('state', (event) => {
        sawFrame = true
        window.clearTimeout(probation)
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
        // explicitly so a tunnel restart cannot leave the page permanently dead.
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
      window.clearTimeout(probation)
      window.clearTimeout(pollTimer)
      window.clearInterval(ticker)
    }
  }, [])

  return { state, connected, staleness, transport }
}
