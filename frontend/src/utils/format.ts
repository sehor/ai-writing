/** Humanize machine values like 'pending_review' into 'pending review'. */
export function statusText(value: string): string {
  const labels: Record<string, string> = {
    pending_review: '待审核', accepted: '已接受', rejected: '已拒绝', draft: '草稿',
    succeeded: '已完成', failed: '失败', queued: '等待中', running: '处理中',
    character: '人物', location: '地点', item: '物品', faction: '组织', rule: '规则',
    chapter_summary: '章节摘要', prose_sample: '正文样本', voice_sample: '人物声音', style_rule: '文风规则',
    critical: '严重', warning: '提醒', info: '提示', human: '作者', ai: 'AI',
    create: '新建', update: '更新', scene: '场景', project: '项目',
    open: '未完结', resolved: '已解决', dormant: '暂伏', active: '进行中',
    brainstorm: '构思灵感', scene_bridge: '场景衔接', conflict_options: '冲突处理',
    character_motivation: '人物动机', canon_gap: '设定缺口', prose_reference: '写作参考', structure_fix: '结构调整',
  }
  return labels[value] ?? value.split('_').join(' ')
}
