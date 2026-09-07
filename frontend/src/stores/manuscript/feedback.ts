import { ref } from 'vue'

/** The workspace has one message surface; operation/session flags stay with their owner. */
export function useManuscriptFeedback() {
  const manuscriptError = ref('')
  const manuscriptStatus = ref('')
  function resetFeedback() {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
  }
  return { manuscriptError, manuscriptStatus, resetFeedback }
}

export type ManuscriptFeedback = Pick<ReturnType<typeof useManuscriptFeedback>, 'manuscriptError' | 'manuscriptStatus'>
