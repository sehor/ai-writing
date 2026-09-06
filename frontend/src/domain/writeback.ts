import type { CanonEntity, StoryThread, WritebackProposal, WritebackTarget } from '../types'

const targetLabels: Record<WritebackTarget, string> = {
  canon_entity: '故事设定', memory_record: 'Memory', narrative_relation: '叙事关系',
  story_thread: 'StoryThread', story_thread_event: 'StoryThread event',
  story_thread_status: 'StoryThread status',
}
export function supportedWriteback(target: string): boolean {
  return Object.prototype.hasOwnProperty.call(targetLabels, target)
}

export function writebackConflict(proposal: WritebackProposal, canon: CanonEntity[], threads: StoryThread[]): string {
  if (!supportedWriteback(proposal.target)) return '不支持的提案类型，不能接受。'
  if (proposal.action !== 'update') return ''
  if (proposal.target === 'story_thread_status') {
    const thread = threads.find((item) => item.id === proposal.target_record_id)
    if (!thread) return '找不到目标 StoryThread，或状态尚未加载。'
    if (thread.status !== proposal.payload.from_state) return 'StoryThread 状态已变化，请重新生成提案。'
    return ''
  }
  if (proposal.target !== 'canon_entity') return '此类型不支持更新操作。'
  const entity = canon.find((item) => item.id === proposal.target_record_id)
  return !entity || entity.version !== proposal.expected_version ? 'Canon 版本已变化或目标不存在，请重新生成提案。' : ''
}
