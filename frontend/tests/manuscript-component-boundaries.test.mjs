import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const manuscriptWorkspace = readFileSync(
  new URL('../src/components/ManuscriptWorkspace.vue', import.meta.url),
  'utf8',
)

const childComponents = [
  'ManuscriptInputs',
  'ReferenceWorkspace',
  'ManuscriptProposalWorkspace',
  'AcceptedManuscript',
  'RevisionHistory',
  'WritebackReview',
]

test('manuscript workspace delegates each major review region to a focused component', () => {
  for (const component of childComponents) {
    assert.match(
      manuscriptWorkspace,
      new RegExp(`import ${component} from './manuscript/${component}\\.vue'`),
    )
    assert.match(manuscriptWorkspace, new RegExp(`<${component} />`))
  }

  assert.doesNotMatch(manuscriptWorkspace, /class="chapter-editor"/)
  assert.doesNotMatch(manuscriptWorkspace, /class="reference-form"/)
  assert.doesNotMatch(manuscriptWorkspace, /class="revision-history"/)
})
