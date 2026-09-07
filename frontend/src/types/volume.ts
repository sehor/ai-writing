export type VolumeDraft = { sequence: number; title: string }
export type ManuscriptVolume = VolumeDraft & { id: string; project_id: string; chapter_ids: string[] }
