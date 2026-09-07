import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'
import { posix } from 'node:path'

const root = new URL('../src/stores/', import.meta.url)
function sourceFiles(directory, prefix = '') {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry =>
    entry.isDirectory()
      ? sourceFiles(new URL(`${entry.name}/`, directory), `${prefix}${entry.name}/`)
      : entry.name.endsWith('.ts') ? [`${prefix}${entry.name}`] : [],
  )
}
const files = sourceFiles(root)
const dependencies = new Map(files.map(name => {
  const source = ts.createSourceFile(name, readFileSync(new URL(name, root), 'utf8'), ts.ScriptTarget.Latest)
  const imports = source.statements.filter(node => ts.isImportDeclaration(node) && !node.importClause?.isTypeOnly)
  return [name, imports.map(node => node.moduleSpecifier.text)
    .filter(path => path.startsWith('.'))
    .map(path => posix.normalize(posix.join(posix.dirname(name), `${path}.ts`)))
    .filter(path => files.includes(path))]
}))

test('domain stores cannot import the workspace or form runtime dependency cycles', () => {
  function visit(name, ancestors = []) {
    assert.ok(!ancestors.includes(name), `Store dependency cycle: ${[...ancestors, name].join(' -> ')}`)
    for (const dependency of dependencies.get(name) ?? []) {
      if (name !== 'workspace.ts') assert.notEqual(dependency, 'workspace.ts', `${name} imports the application shell`)
      visit(dependency, [...ancestors, name])
    }
  }
  for (const name of dependencies.keys()) visit(name)
  assert.deepEqual(dependencies.get('projectContext.ts'), [], 'Selection context must remain a leaf store')
})
