import {test, expect, type Page} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const axe = async (page: Page) => {
  const issues = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa']).analyze();
  return issues.violations.map(v => ({id: v.id, nodes: v.nodes.map(n => n.target)}));
};
// The evidence editor is CodeMirror once its chunk has loaded (a plain textarea before that).
const editorReady = (page: Page) => expect(page.locator('.cm-content')).toBeVisible();
const evidence = (page: Page) => page.getByRole('textbox', {name: '调用证据', exact: true});
const runCheck = (page: Page) => page.getByRole('button', {name: '运行检查', exact: true}).click();
const checkRequest = (page: Page) => page.waitForRequest(r => r.url().endsWith('/api/check') && r.method() === 'POST');

for (const theme of ['dark', 'light'] as const) {
  for (const path of ['/docs', '/workbench']) {
    test(`reviewer ${theme} 320px ${path === '/docs' ? 'docs' : 'empty-state'}`, async ({page}) => {
      await page.setViewportSize({width: 320, height: 720});
      await page.emulateMedia({colorScheme: theme, reducedMotion: 'reduce'});
      await page.goto(path);
      if (path === '/workbench') await editorReady(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), path).toBe(true);
      expect(await axe(page)).toEqual([]);
      if (path === '/docs') {
        // The user guide is reachable by keyboard; long commands scroll horizontally inside their block.
        const guide = page.locator('.doc-index-lead').getByRole('link', {name: '本地运行指南'});
        await guide.focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/docs\/27-local-development-guide$/);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const scrolling = page.getByRole('region', {name: '代码示例，可横向滚动'}).first();
        await scrolling.focus();
        await expect(scrolling).toBeFocused();
        await scrolling.press('ArrowRight');
        await expect.poll(() => scrolling.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
      }
      await page.screenshot({path: `../artifacts/ui05-review-${theme}-${path === '/docs' ? 'docs' : 'empty'}-320.png`, fullPage: true});
    });
  }

  test(`reviewer ${theme} results for every built-in sample are axe-clean without overflow`, async ({page}) => {
    await page.setViewportSize({width: 390, height: 844});
    await page.emulateMedia({colorScheme: theme, reducedMotion: 'reduce'});
    await page.goto('/workbench');
    await editorReady(page);
    for (const [sample, verdict] of [['结果类型不符', '不通过'], ['正常调用', '通过'], ['缺失结果', '无法判定']] as const) {
      await page.getByRole('button', {name: sample, exact: true}).click();
      await runCheck(page);
      await expect(page.getByRole('heading', {name: verdict, exact: true})).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), sample).toBe(true);
      expect(await axe(page), sample).toEqual([]);
    }
  });
}

test('reviewer sidebar keyboard navigation keeps the draft on cancel, then leaves', async ({page}) => {
  await page.goto('/workbench');
  await editorReady(page);
  await evidence(page).fill('{"local_draft":true}');
  const docs = page.getByRole('navigation', {name: '帮助'}).getByRole('link', {name: '文档', exact: true});
  const dialog = page.getByRole('dialog', {name: '离开调用检查？'});
  await docs.focus();
  await page.keyboard.press('Enter');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', {name: '留在此页'}).click();
  await expect(page).toHaveURL(/\/workbench$/);
  await expect(evidence(page)).toHaveText('{"local_draft":true}');
  await docs.focus();
  await page.keyboard.press('Enter');
  await dialog.getByRole('button', {name: '离开', exact: true}).click();
  await expect(page).toHaveURL(/\/docs$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/workbench$/);
  await editorReady(page);
  await expect(evidence(page)).toHaveText('{"local_draft":true}');
});

test('reviewer replacing a draft asks first and keeps it on cancel', async ({page}) => {
  await page.goto('/workbench');
  await editorReady(page);
  await evidence(page).fill('{"keep":1}');
  await page.getByRole('button', {name: '正常调用', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: '替换编辑器中的内容？'});
  await dialog.getByRole('button', {name: '取消'}).click();
  await expect(evidence(page)).toHaveText('{"keep":1}');
  await page.getByRole('button', {name: '正常调用', exact: true}).click();
  await dialog.getByRole('button', {name: '替换'}).click();
  await expect(page.getByRole('button', {name: '正常调用', exact: true})).toHaveAttribute('aria-pressed', 'true');
});

test('reviewer evidence bytes stay exact: BOM + CRLF import, lossless format, shortcut run', async ({page}) => {
  await page.goto('/workbench?source=custom');
  await editorReady(page);
  const raw = Buffer.from('﻿{\r\n"id": 9007199254740993.10, "s": "a\\u00e9\\/",\r\n"n": [1E400, -0.0, {}], "e": []}\r\n', 'utf8');
  await page.getByLabel('导入 JSON 文件').setInputFiles({name: 'crlf.json', mimeType: 'application/json', buffer: raw});
  await expect(page.locator('#evidence-status')).toContainText('CRLF');
  let request = checkRequest(page);
  await runCheck(page);
  expect((await request).postDataBuffer()).toEqual(raw);
  await expect(page.getByText('invalid_document', {exact: true})).toBeVisible();

  await page.getByRole('button', {name: '格式化'}).click();
  await evidence(page).click();
  request = checkRequest(page);
  await page.keyboard.press('ControlOrMeta+Enter');
  const formatted = '﻿{\r\n  "id": 9007199254740993.10,\r\n  "s": "a\\u00e9\\/",\r\n  "n": [\r\n    1E400,\r\n    -0.0,\r\n    {}\r\n  ],\r\n  "e": []\r\n}\r\n';
  expect((await request).postDataBuffer()).toEqual(Buffer.from(formatted, 'utf8'));
});

test('reviewer syntax errors show line and column; findings locate the field', async ({page}) => {
  await page.goto('/workbench');
  await editorReady(page);
  await runCheck(page);
  await expect(page.getByRole('heading', {name: '不通过', exact: true})).toBeVisible();
  const finding = page.getByRole('button', {name: /返回结果不符合契约/});
  await expect(finding).toContainText('类型不符：应为 integer，实际为 string');
  await expect(finding).toContainText('第 40 行');
  await expect(page.getByLabel('字段路径 /result/structured_content/count')).toBeVisible();
  await finding.click();
  await expect(page.locator('.cm-wb-target')).toHaveText('"count": "2"');

  await evidence(page).fill('{"a": 1,}');
  await expect(page.getByRole('heading', {name: '不通过', exact: true})).toHaveCount(0);
  await expect(page.locator('#evidence-status')).toContainText('第 1 行第 9 列：最后一个字段后面不能有逗号');
  await expect(page.getByRole('button', {name: '格式化'})).toBeDisabled();
  await expect(page.locator('.cm-lintRange-error')).toHaveCount(1);
});

test('reviewer dropping a file onto the editor imports it unchanged', async ({page}) => {
  await page.goto('/workbench');
  await editorReady(page);
  const transfer = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(new File(['{"dropped": 1.50}'], 'drop.json', {type: 'application/json'}));
    return data;
  });
  await page.locator('.wb-code').dispatchEvent('drop', {dataTransfer: transfer});
  await expect(evidence(page)).toHaveText('{"dropped": 1.50}');
  const request = checkRequest(page);
  await runCheck(page);
  expect((await request).postData()).toBe('{"dropped": 1.50}');
});
