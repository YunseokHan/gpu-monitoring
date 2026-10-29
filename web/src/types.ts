/** Mirrors hub/gpu_hub/models.py. */

export interface ProcInfo {
  pid: number
  name: string
  cmdline: string
  user: string
  used_mem_mb: number | null
  kind: 'C' | 'G'
  is_dummy: boolean
}

export interface GpuSnapshot {
  index: number
  uuid: string
  name: string
  mem_used_mb: number
  mem_total_mb: number
  util_gpu: number | null
  util_mem: number | null
  temp_c: number | null
  power_w: number | null
  power_limit_w: number | null
  processes: ProcInfo[]
  dummy_active: boolean
  dummy_pid: number | null
  dummy_backend: string | null
  dummy_error: string | null
  dummy_enabled: boolean
}

export type NodeStatus = 'online' | 'stale' | 'offline'

export interface NodeView {
  node_id: string
  node_index: number
  cluster: string
  hostname: string
  ts: number
  agent_version: string
  driver_version: string | null
  cuda_version: string | null
  gpus: GpuSnapshot[]
  error: string | null
  status: NodeStatus
  age_s: number
}

export interface QuotaUser {
  user: string
  used_s: number
}

/** A Slurm site's allocation. Seconds are as the site reports them; `unit` says of what. */
export interface QuotaView {
  cluster: string
  label: string
  account: string
  source: string
  unit: 'node' | 'gpu'
  gpus_per_node: number
  period_start: string
  period_end: string
  contract_s: number
  used_s: number
  users: QuotaUser[]
  ts: number
  source_ts: number | null
  error: string | null
  status: NodeStatus
  age_s: number
}

export interface ClusterState {
  ts: number
  nodes: NodeView[]
  quotas: QuotaView[]
}
