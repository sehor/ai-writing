import type { ObjectDirective } from 'vue'

function resize(element: HTMLTextAreaElement) {
  const scroll = element.closest('.editor-scroll')
  const top = scroll?.scrollTop ?? 0
  element.style.height = 'auto'
  element.style.height = `${element.scrollHeight}px`
  if (scroll) scroll.scrollTop = top
}
export const vAutosize: ObjectDirective<HTMLTextAreaElement> = {
  mounted(element) {
    resize(element)
    element.addEventListener('input', onInput)
  },
  updated(element) {
    resize(element)
  },
  beforeUnmount(element) {
    element.removeEventListener('input', onInput)
  },
}
function onInput(event: Event) {
  resize(event.target as HTMLTextAreaElement)
}
