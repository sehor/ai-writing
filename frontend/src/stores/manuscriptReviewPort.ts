import type { ManuscriptRevision } from '../types'

/** Wired by the application shell; neither domain imports the other store. */
export interface ManuscriptReviewPort {
  loadWritebackProposals(projectId: string): Promise<void>
  loadPostAcceptAnalysisJobs(projectId: string): Promise<void>
  showLatestConsistencyReport(projectId: string): Promise<void>
}

export type ManuscriptRevisionSource = (projectId: string) => readonly ManuscriptRevision[]
