export type GraphNode = {
  id: string
  label: string
  node_type: string
  status: string
}

export type GraphEdge = {
  source: string
  target: string
  edge_type: string
  label: string
}

export type GraphRisk = {
  id: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  detail: string
  source_id: string
}

export type GraphAnalysisSummary = {
  node_count: number
  edge_count: number
  risk_count: number
  critical_count: number
  warning_count: number
  unresolved_thread_count: number
  canon_reference_count: number
}

export type GraphAnalysisResponse = {
  project_id: string
  summary: GraphAnalysisSummary
  nodes: GraphNode[]
  edges: GraphEdge[]
  risks: GraphRisk[]
}
