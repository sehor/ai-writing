/** Humanize machine values like 'pending_review' into 'pending review'. */
export function statusText(value: string): string {
  return value.split('_').join(' ')
}
