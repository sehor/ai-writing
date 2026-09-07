export type WorkflowAgentTrace = {
  stage: string
  agent_name: string
  status: string
}

export type WorkflowRuntimeStatus = {
  runtime: 'local_deterministic' | `provider_${string}`
  runtime_kind?: 'local_deterministic' | 'model_gateway' | null
  provider: string
  provider_configured: boolean
  model: string
  base_url: string
  details: string
}

export type ModelCapabilities = {
  text_generation: boolean
  json_mode: boolean
  json_schema: boolean
  temperature: boolean
  max_output_tokens: boolean
  timeout: boolean
  seed: boolean
  reasoning: boolean
  tools: boolean
  streaming: boolean
  vision: boolean
  usage_reporting: boolean
  finish_reason: boolean
  request_id: boolean
  context_window_tokens: number
  max_completion_tokens: number
}

export type ModelProfile = {
  id: string
  label: string
  provider: string
  model: string
  configured: boolean
  capabilities: ModelCapabilities
  fallback_profile_ids: string[]
}

export type ModelExecutionOptions = {
  model_profile: string
  allow_fallback: boolean
  allow_repair: boolean
}
