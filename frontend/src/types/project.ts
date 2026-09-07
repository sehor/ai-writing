export type ProjectSummary = {
  id: string
  title: string
  premise: string
  current_step: number
}

export type ActiveSection = 'snowflake' | 'canon' | 'memory' | 'graph' | 'manuscript'

// P2-07 on the frontend: project backup / restore packages.

export type BackupPreviewSummary = {
  format_version: number
  legacy_incomplete: boolean
  can_overwrite: boolean
  warnings: string[]
  blocking_errors: string[]
  project: {
    id: string
    title: string
    row_counts: Record<string, number>
  }
  schema_version: number
  current_schema_version: number
  module_file_count: number
  target_exists: boolean
  would_replace_existing_project: boolean
}

export type BackupImportSummary = {
  format_version: number
  legacy_incomplete: boolean
  project: {
    id: string
    title: string
    row_counts: Record<string, number>
  }
  replaced_existing: boolean
  restored_tables: Record<string, number>
  restored_module_files: number
}
