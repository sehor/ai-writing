import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

const root = new URL('../src/stores/', import.meta.url)
const dependencies = new Map(readdirSync(root).filter(name => name.endsWith('.ts')).map(name => {
  const source = ts.createSourceFile(name, readFileSync(new URL(name, root), 'utf8'), ts.ScriptTarget.Latest)
  const imports = source.statements.filter(node => ts.isImportDeclaration(node) && !node.importClause?.isTypeOnly)
  return [name, imports.map(node => node.moduleSpecifier.text).filter(path => path.startsWith('./')).map(path => `${path.slice(2)}.ts`)]
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
