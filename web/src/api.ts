const params = new URLSearchParams(window.location.search)

/** Control token, passed as ?k=... on the embed URL. Absent => read-only dashboard. */
export const controlToken = params.get('k') ?? ''

/** ?theme=dark|light pins the theme; Notion cannot tell an iframe which theme it is in. */
export const forcedTheme = params.get('theme')

export class ControlError extends Error {}

export async function setDummy(
  nodeId: string,
  gpuIndex: number | null,
  enabled: boolean,
): Promise<void> {
  const response = await fetch(`/api/v1/nodes/${encodeURIComponent(nodeId)}/dummy`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Control-Token': controlToken,
    },
    body: JSON.stringify({ gpu_index: gpuIndex, enabled }),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new ControlError(
      response.status === 401
        ? 'This dashboard link cannot change anything (missing or wrong ?k= token).'
        : `Hub rejected the change (HTTP ${response.status}). ${detail.slice(0, 200)}`,
    )
  }
}
