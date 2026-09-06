import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { chromium } from 'playwright'

// Isolated API fixtures: this suite never touches the author's database or models.
const root = fileURLToPath(new URL('..', import.meta.url))
const output = fileURLToPath(new URL('../../.tmp/ui-review/', import.meta.url))
await mkdir(output, { recursive: true })
const project = {
  id: 'ui-review',
  title: '雾港来信',
  premise: '一名修复旧信的年轻人，在即将沉没的港城里寻找一封从未寄出的信。',
  current_step: 1,
}
const chapters = [
  {
    id: 'chapter-1',
    project_id: project.id,
    sequence: 1,
    title: '第一章 · 潮水退去之后',
    summary: '许知微回到雾港，收到一封没有署名的信。',
  },
  {
    id: 'chapter-2',
    project_id: project.id,
    sequence: 2,
    title: '第二章 · 信上的盐',
    summary: '',
  },
]
const scenes = ['灯塔下的来信', '旧邮局的陌生人', '没有寄出的告别'].map(
  (title, i) => ({
    id: `scene-${i + 1}`,
    project_id: project.id,
    chapter_id: chapters[i === 2 ? 1 : 0].id,
    sequence: i + 1,
    title,
    pov: '许知微',
    source_snowflake_step: 8,
    goal: '找到信的主人',
    conflict: '信上的地址早已被海水淹没',
    turning_point: '信纸背后藏着新的线索',
    outcome: '',
    information_delta: '',
    character_state_delta: '',
    required_canon_ids: [],
    forbidden_facts: [],
    open_threads: [],
  }),
)
const prose =
  '潮水退去的时候，雾港终于安静下来。\n\n许知微站在灯塔下，看见一封信卡在生锈的铁门缝里。信封已经被海风吹得发软，边角结着细细的盐。她认得那种纸——很多年前，母亲的书桌上总是放着一叠。\n\n她没有立刻拆开。远处的渡轮鸣了一声，像有人隔着整个海湾叹气。\n\n“你来晚了。”\n\n守塔人从门后探出头。他的目光越过许知微，落在她手里的信上，停了片刻。\n\n“这封信，”他慢慢地说，“已经在这里等了你十七年。”'
let manuscripts = scenes.slice(0, 2).map((scene, i) => ({
  id: `text-${i}`,
  project_id: project.id,
  scene_id: scene.id,
  proposal_id: `old-${i}`,
  title: scene.title,
  content: i ? '邮局在街角的阴影里。' : prose,
  version: 1,
  accepted_at: '2026-09-06T07:00:00Z',
}))
let proposals = [
  {
    id: 'proposal-3',
    project_id: project.id,
    scene_id: 'scene-3',
    title: scenes[2].title,
    content: '她终于拆开了那封信。',
    context: '场景契约',
    checklist: ['叙述视角一致'],
    status: 'pending_review',
    created_at: 'now',
    reviewed_at: '',
  },
]
let writes = 0
const failures = []
const server = await createServer({
  root,
  server: { host: '127.0.0.1', port: 0, strictPort: false },
})
let browser
try {
  await server.listen()
  const url = `http://127.0.0.1:${server.httpServer.address().port}`
  browser = await chromium.launch()
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  })
  page.on('pageerror', (error) => {
    failures.push(error.message)
    console.error('Page error:', error.message)
  })
  page.on('console', (message) => {
    if (message.type() === 'error') console.error('Browser:', message.text())
  })
  page.on('requestfailed', (request) =>
    console.error('Request failed:', request.url(), request.failure()),
  )
  page.on('dialog', (dialog) => dialog.accept())
  await page.route(`${url}/api/**`, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api', '')
    let data = []
    if (request.method() === 'PUT' && path.includes('/manuscript/scenes/')) {
      writes++
      const body = request.postDataJSON()
      const scene = manuscripts.find(
        (item) => item.scene_id === path.split('/').at(-1),
      )
      assert.equal(body.expected_scene_version, scene.version)
      Object.assign(scene, {
        title: body.title,
        content: body.content,
        version: scene.version + 1,
      })
      data = scene
    } else if (path.endsWith('/health')) data = { status: 'ok' }
    else if (path === '/projects') data = [project]
    else if (path === '/snowflake/steps')
      data = [
        {
          number: 1,
          title: '一句话故事',
          artifact: 'one_sentence',
          description: '用一句话抓住故事的核心。',
        },
      ]
    else if (path.endsWith('/snowflake/workflow/status'))
      data = {
        runtime: 'local_deterministic',
        runtime_kind: 'local_deterministic',
        provider: 'local',
        provider_configured: false,
      }
    else if (path.endsWith('/snowflake/steps')) data = []
    else if (/snowflake\/artifacts\/\d+\/revisions/.test(path))
      data = {
        data: [],
        page: 1,
        page_size: 100,
        total_items: 0,
        total_pages: 0,
      }
    else if (path.endsWith('/manuscript/chapters')) data = chapters
    else if (path.endsWith('/scene-contracts')) data = scenes
    else if (path.endsWith('/manuscript/scenes')) data = manuscripts
    else if (path.endsWith('/manuscript/proposals')) data = proposals
    else if (path.endsWith('/canon/entities'))
      data = [
        {
          id: 'canon-1',
          project_id: project.id,
          entity_type: 'character',
          name: '许知微',
          summary: '旧信修复师，离开雾港十七年后归来。',
          current_state: '刚收到匿名来信',
          constraints: '不知道母亲的去向',
          last_seen: '第一章',
          timeline_notes: '',
        },
        {
          id: 'canon-2',
          entity_type: 'location',
          name: '雾港灯塔',
          summary: '港城最古老的建筑。',
          current_state: '',
          constraints: '',
          last_seen: '',
          timeline_notes: '',
        },
      ]
    else if (path.endsWith('/memory/records')) data = []
    else if (path.endsWith('/graph/analysis'))
      data = {
        project_id: project.id,
        summary: {
          node_count: 3,
          edge_count: 2,
          risk_count: 1,
          critical_count: 0,
          warning_count: 1,
          unresolved_thread_count: 1,
          canon_reference_count: 1,
        },
        nodes: [],
        edges: [],
        risks: [
          {
            id: 'risk-1',
            severity: 'warning',
            title: '这封信的来历尚未交代',
            detail: '检查下一场景是否延续了信的线索。',
            source_id: 'scene-1',
          },
        ],
      }
    else if (path.includes('/narrative/director')) data = null
    else if (path.endsWith('/manuscript-progress'))
      data = {
        total_scenes: 3,
        accepted_scenes: 2,
        pending_scenes: 1,
        stale_scenes: 0,
      }
    else if (request.method() !== 'GET')
      throw new Error(`Unexpected mutation: ${request.method()} ${path}`)
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(data),
    })
  })
  await page.goto(url)
  await page.screenshot({ path: `${output}/initial.png` })
  const editor = page.getByRole('textbox', { name: '正文内容', exact: true })
  await editor.waitFor({ timeout: 15000 }).catch(async (error) => {
    console.error(await page.locator('body').innerText())
    await page.screenshot({ path: `${output}/failure.png` })
    throw error
  })
  assert.equal(await editor.inputValue(), prose)
  await page.screenshot({ path: `${output}/writing-light.png` })
  await editor.fill(prose + '\n\n她把信放进了口袋。')
  await page.getByText('已暂存本机 · 尚未保存版本', { exact: true }).waitFor()
  await editor.press('Control+s')
  await page.getByText('已保存 · 版本 2', { exact: true }).waitFor()
  assert.equal(await editor.inputValue(), manuscripts[0].content)
  assert.equal(
    await editor.evaluate((el) => el === document.activeElement),
    true,
  )
  await page.getByRole('button', { name: '进入专注模式' }).click()
  assert.equal(await page.locator('.sidebar').isVisible(), false)
  await page.keyboard.press('Escape')
  assert.equal(await page.locator('.sidebar').isVisible(), true)
  await page.getByRole('button', { name: '参考资料', exact: true }).click()
  await page.getByRole('complementary', { name: '写作辅助面板' }).waitFor()
  await page.screenshot({ path: `${output}/writing-reference.png`, animations: 'disabled' })
  await page.getByRole('button', { name: '关闭辅助面板' }).click()
  await page.getByRole('button', { name: '切换深色主题' }).click()
  await page.screenshot({ path: `${output}/writing-dark.png` })
  await page.getByRole('button', { name: '没有寄出的告别 待审' }).click()
  const draft = page.getByRole('textbox', { name: 'AI 草稿正文', exact: true })
  await draft.fill('作者保留的修改。')
  await draft.press('Control+s')
  assert.equal(writes, 1, 'Ctrl+S in a proposal must never accept it')
  await page.screenshot({ path: `${output}/proposal-dark.png` })
  await page.reload()
  await page.getByRole('button', { name: /待审核草稿/ }).click()
  await draft.waitFor()
  assert.equal(await draft.inputValue(), '作者保留的修改。')
  await page.getByRole('button', { name: '故事设定', exact: true }).click()
  await page.getByPlaceholder('搜索设定').fill('许知微')
  assert.equal(await page.locator('.canon-list > button').count(), 1)
  await page.screenshot({ path: `${output}/canon-dark.png` })
  await page.getByRole('button', { name: '切换浅色主题' }).click()
  await page.getByRole('button', { name: '雪花规划', exact: true }).click()
  await page.screenshot({ path: `${output}/snowflake-light.png` })
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  await page.getByRole('button', { name: '灯塔下的来信', exact: true }).click()
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 800 })
    await page.screenshot({ path: `${output}/writing-${width}.png` })
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
      `No page overflow at ${width}`,
    )
    assert.equal(await editor.isVisible(), true)
  }
  await page.getByRole('button', { name: '展开章节目录' }).click()
  await page.getByRole('complementary', { name: '章节目录' }).waitFor()
  await page
    .getByRole('button', { name: '旧邮局的陌生人', exact: true })
    .click()
  assert.equal(await editor.inputValue(), manuscripts[1].content)
  assert.deepEqual(failures, [])
  console.log(
    `PASS: desktop/mobile, themes, save continuity, draft-only shortcut, reload recovery, navigation and search. Screenshots: ${output}`,
  )
} finally {
  await browser?.close()
  await server.close()
}
