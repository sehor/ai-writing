import type { ProjectSummary, SnowflakeStep } from '../types'

/**
 * The slice of the workspace shell that domain stores are allowed to read.
 * Declared as a standalone leaf type so domain stores can consume the
 * workspace store lazily without creating a circular type inference between
 * the workspace store and the stores it orchestrates.
 */
export interface WorkspaceShell {
  reloadActiveProject(): void
  activeProjectId: string
  activeProject: ProjectSummary | undefined
  activeStepNumber: number
  activeStep: SnowflakeStep | undefined
}
