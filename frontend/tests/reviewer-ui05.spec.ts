import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

for (const theme of ['dark','light'] as const) {
  test(`reviewer ${theme} 320px docs and empty-state`, async ({page}) => {
    await page.setViewportSize({width:320,height:720});
    await page.emulateMedia({colorScheme:theme,reducedMotion:'reduce'});
    for (const path of ['/docs','/workbench']) {
      await page.goto(path);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),path).toBe(true);
      const issues=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa']).analyze();
      expect(issues.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([]);
      if (path==='/docs') {
        const toc=page.getByRole('navigation',{name:'文档章节'});
        await toc.getByRole('link',{name:'怎么测试 Agent',exact:true}).focus();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/#agent-testing$/);
        for (const selector of ['.docs-table-scroll', '.docs-code']) {
          const scrolling=page.locator(selector);
          await scrolling.focus();
          await expect(scrolling).toBeFocused();
          await scrolling.press('ArrowRight');
          await expect.poll(()=>scrolling.evaluate(el=>el.scrollLeft)).toBeGreaterThan(0);
        }
      }
      await page.screenshot({path:`../artifacts/ui05-review-${theme}-${path==='/docs'?'docs':'empty'}-320.png`,fullPage:true});
    }
  });
}

test('reviewer footer docs keyboard navigation preserves cancel then accepts',async({page})=>{
  await page.goto('/workbench');
  const editor=page.getByRole('textbox',{name:'调用证据',exact:true});
  await editor.fill('{"local_draft":true}');
  const docs=page.getByRole('region',{name:'产品信息'}).getByRole('link',{name:'项目文档',exact:true});
  await docs.focus();
  page.once('dialog',dialog=>dialog.dismiss());
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/workbench$/);
  await expect(editor).toHaveValue('{"local_draft":true}');
  await docs.focus();
  page.once('dialog',dialog=>dialog.accept());
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/docs$/);
});
