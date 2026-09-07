import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const schemas = JSON.parse(readFileSync(new URL('../../contracts/api-dtos.json', import.meta.url), 'utf8'))

// This deliberately covers only the JSON output shapes used here. Unknown schema
// constructs fail instead of silently weakening a contract to `any`.
function typeOf(schema, root) {
  if (schema.$ref) return typeOf(root.$defs[schema.$ref.split('/').at(-1)], root)
  if (schema.const !== undefined) return JSON.stringify(schema.const)
  if (schema.enum) return schema.enum.map((value) => JSON.stringify(value)).join(' | ')
  if (schema.anyOf) return schema.anyOf.map((value) => `(${typeOf(value, root)})`).join(' | ')
  switch (schema.type) {
    case 'string': return 'string'
    case 'integer': case 'number': return 'number'
    case 'boolean': return 'boolean'
    case 'null': return 'null'
    case 'array': return `Array<${typeOf(schema.items, root)}>`
    case 'object':
      assert.ok(schema.properties, 'Expected a DTO with named properties')
      // FastAPI output serializes defaults too; request optionality is not UI optionality.
      return `{ ${Object.entries(schema.properties).map(([key, value]) => `${JSON.stringify(key)}: ${typeOf(value, root)}`).join('; ')} }`
    default: throw new Error(`Unsupported output schema: ${JSON.stringify(schema)}`)
  }
}

test('critical frontend DTO fields match the backend output schemas', () => {
  const names = Object.keys(schemas)
  const file = fileURLToPath(new URL('./api-dto-contract.virtual.ts', import.meta.url)).replaceAll('\\', '/')
  const text = [
    `import type { ${names.join(', ')} } from '../src/types'`,
    'type Assert<T extends true> = T',
    'type Same<A, B> = [A] extends [B] ? [B] extends [A] ? true : false : false',
    ...names.flatMap((name) => [
      `type Api${name} = ${typeOf(schemas[name], schemas[name])}`,
      `type Fields${name} = Assert<Same<keyof ${name}, keyof Api${name}>>`,
      // Old frontend fixtures may omit server-default metadata. Its type must
      // still match; the server output contract always contains these fields.
      `type Values${name} = Assert<Same<Required<${name}>, Api${name}>>`,
    ]),
  ].join('\n')
  const options = { strict: true, noEmit: true, skipLibCheck: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, types: [] }
  const host = ts.createCompilerHost(options)
  const original = host.getSourceFile.bind(host)
  host.getSourceFile = (path, languageVersion, ...rest) => path === file
    ? ts.createSourceFile(path, text, languageVersion, true)
    : original(path, languageVersion, ...rest)
  const program = ts.createProgram([file], options, host)
  const diagnostics = ts.getPreEmitDiagnostics(program)
  assert.deepEqual(diagnostics.map((d) => `${d.file?.fileName}:${d.file?.getLineAndCharacterOfPosition(d.start ?? 0).line + 1}: ${ts.flattenDiagnosticMessageText(d.messageText, '\n')}`), [])
})
