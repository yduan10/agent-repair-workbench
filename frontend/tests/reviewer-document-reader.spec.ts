import {test,expect} from '@playwright/test';
import {readdirSync} from 'node:fs';
import {resolve} from 'node:path';

const docs=readdirSync(resolve('..','docs'),{recursive:true}).filter((name):name is string=>typeof name==='string'&&name.endsWith('.md'));
const routes=['/docs/getting-started',...docs.map(file=>'/docs/'+(file==='README.md'?'index':file.slice(0,-3)))];

test('reviewer all registered docs TOCs and local cross-links resolve',async({page,request})=>{
  test.setTimeout(90000);
  const broken:unknown[]=[];
  const localLinks=new Set<string>();
  for(const path of routes){
    const response=await page.goto(path);
    if(response?.status()!==200){broken.push({path,status:response?.status()});continue;}
    const missing=await page.locator('.document-toc a').evaluateAll(links=>links.flatMap(link=>{
      const href=link.getAttribute('href')!;
      return document.getElementById(decodeURIComponent(href.slice(1)))?[]:[href];
    }));
    if(missing.length)broken.push({path,missing});
    for(const href of await page.locator('.markdown-document a[href^="/docs/"]').evaluateAll(links=>links.map(link=>link.getAttribute('href')!)))localLinks.add(href);
    const ids=await page.locator('[id]').evaluateAll(nodes=>nodes.map(node=>node.id));
    if(new Set(ids).size!==ids.length)broken.push({path,duplicate_ids:ids.filter((id,i)=>ids.indexOf(id)!==i)});
  }
  for(const link of localLinks){const result=await request.get(link);if(result.status()!==200)broken.push({link,status:result.status()});}
  console.log(JSON.stringify({pages:routes.length,localLinks:localLinks.size,broken}));
  expect(broken).toEqual([]);
});

test('reviewer source routes reject file-like and traversal requests',async({request})=>{
  for(const path of ['/docs/not-registered.md','/docs/%2e%2e%2f.env','/docs/%2Fetc%2Fpasswd','/docs/../../.env','/docs/reviews/not-a-review']){
    const response=await request.get(path);
    expect([400,404]).toContain(response.status());
  }
});

for(const [theme,width] of [['dark',390],['light',1440]] as const){
  test(`reviewer ${theme} ${width} keyboard reading and screenshot`,async({page})=>{
    await page.setViewportSize({width,height:900});
    await page.emulateMedia({colorScheme:theme,reducedMotion:'reduce'});
    await page.goto('/docs/02-architecture');
    if(width===390){
      const summary=page.locator('.document-mobile-toc summary');
      await summary.focus();await summary.press('Enter');
      const toc=page.getByRole('navigation',{name:'本页章节（移动版）'});
      await expect(toc).toBeVisible();
      await toc.getByRole('link').first().focus();await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/#/);
      const table=page.locator('.markdown-table').first();
      await table.focus();await table.press('ArrowRight');
      await expect.poll(()=>table.evaluate(el=>el.scrollLeft)).toBeGreaterThan(0);
    }
    await page.screenshot({path:`../artifacts/ui06-${theme}-${width}.png`,fullPage:true});
  });
}

test('reviewer unsupported diagram falls back to source without external requests',async({page})=>{
  const external:string[]=[];
  page.on('request',r=>{if(!r.url().startsWith(`http://127.0.0.1:${process.env.PW_PORT||'3010'}/`)&&!r.url().startsWith('data:'))external.push(r.url());});
  await page.route('**/docs/02-architecture',async route=>{
    const response=await route.fetch();
    await route.fulfill({response,body:(await response.text()).replaceAll('flowchart LR','flowchart XX')});
  });
  await page.goto('/docs/02-architecture');
  await expect(page.getByText('图表暂未渲染，可展开源码阅读。')).toBeVisible();
  await page.locator('.document-diagram summary').click();
  await expect(page.getByRole('region',{name:'图表源码，可横向滚动'})).toContainText('flowchart XX');
  await expect(page.locator('.document-diagram img')).toHaveCount(0);
  expect(external).toEqual([]);
});

test('reviewer rapid theme changes keep final SVG theme and source readable',async({page})=>{
  await page.goto('/docs/02-architecture');
  const image=page.locator('.document-diagram img');
  await expect(image).toBeVisible();
  const theme=page.getByRole('combobox',{name:'外观主题'});
  const style=async()=>{
    const src=await image.getAttribute('src');
    return src?decodeURIComponent(src.split(',')[1]).match(/<style>([\s\S]*?)<\/style>/)?.[1]:undefined;
  };
  await theme.selectOption('light');
  const light=await style();
  await theme.selectOption('dark');
  await expect.poll(style).not.toBe(light);
  const dark=await style();
  expect(dark).toBeTruthy();
  await theme.selectOption('light');await theme.selectOption('dark');
  await expect.poll(style).toBe(dark);
  const svg=decodeURIComponent((await image.getAttribute('src'))!.split(',')[1]);
  expect(svg).not.toMatch(/<script|<foreignObject/i);
  await expect.poll(()=>image.evaluate(el=>(el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
});

test('reviewer diagram closeup',async({page})=>{
  await page.setViewportSize({width:1440,height:900});
  await page.goto('/docs/02-architecture');
  await expect(page.locator('.document-diagram img')).toBeVisible();
  await expect.poll(()=>page.locator('.document-diagram img').evaluate(el=>(el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await page.locator('.document-diagram').screenshot({path:'../artifacts/ui06-diagram-closeup.png'});
});
