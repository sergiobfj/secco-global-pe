/* QA isolado: não acessa Google, portas operacionais ou banco persistente. */
const { chromium } = require(process.argv[2] || '@playwright/test');
const { acquireQA } = require('./qa-guard.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const output = path.resolve('artifacts/stage061');
(async () => {
  const browser = await chromium.launch({executablePath:process.env.QA_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  let qa;
  const layouts=[], flows=[];
  try {
    qa=await acquireQA(browser,process.env.QA_BASE_URL);
    assert.equal(qa.authMode,'synthetic');
    await fs.mkdir(output,{recursive:true});
    async function capture(page,name,width) {
      await page.evaluate(()=>document.fonts.ready);
      const metrics=await page.evaluate(()=>({
        scrollWidth:document.documentElement.scrollWidth,
        overflow:[...document.querySelectorAll('main *')].filter(el=>{
          if(el.closest('.day-strip'))return false;
          const r=el.getBoundingClientRect();return r.width>0&&(r.left < -1 || r.right > innerWidth+1);
        }).map(el=>el.tagName+'.'+el.className),
        fonts:document.fonts.check('16px "Manrope"')&&document.fonts.check('16px "Space Grotesk"')
      }));
      assert.ok(metrics.scrollWidth<=width,JSON.stringify({name,width,...metrics}));
      assert.deepEqual(metrics.overflow,[],name+' '+width);
      assert.ok(metrics.fonts);
      await page.screenshot({path:path.join(output,name+'-'+width+'.png'),fullPage:true});
      layouts.push({name,width,...metrics});
    }
    for(const width of [360,390,768,1280]) {
      const context=await browser.newContext({extraHTTPHeaders:qa.headers,viewport:{width,height:900},locale:'pt-BR'});
      let corrupt=true;
      const origins=[], errors=[];
      await context.route('**/*',async route=>{
        const req=route.request(),url=new URL(req.url());
        if(url.origin===qa.base) {
          if(req.method()==='POST'&&url.pathname==='/auth/google')origins.push(await req.headerValue('origin'));
          return route.continue();
        }
        if(url.origin==='https://accounts.google.com'&&url.pathname==='/o/oauth2/v2/auth') {
          assert.equal(url.searchParams.get('code_challenge_method'),'S256');
          assert.equal(url.searchParams.get('scope'),'openid email');
          if(corrupt)url.searchParams.set('nonce','synthetic-invalid-browser-nonce');
          return route.fulfill({status:302,headers:{location:qa.base+'/__qa__/authorize?'+url.searchParams.toString()}});
        }
        return route.abort();
      });
      const page=await context.newPage();page.setDefaultTimeout(10000);
      page.on('pageerror',e=>errors.push(e.message));
      page.on('console',m=>{if(m.type()==='error'&&!/401|403|503/.test(m.text()))errors.push(m.text());});
      await page.goto(qa.base+'/login');
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Ir para o conteúdo');
      await capture(page,'login',width);
      await page.getByRole('button',{name:/Entrar com Google/}).click();
      await page.getByRole('heading',{name:'Vamos tentar novamente?'}).waitFor();
      assert.equal(await page.locator('form').count(),0);
      await capture(page,'callback-erro',width);
      await page.getByRole('link',{name:/Tentar novamente/}).click();
      await page.waitForURL(qa.base+'/login');
      corrupt=false;
      await page.getByRole('button',{name:/Entrar com Google/}).click();
      await page.waitForURL(qa.base+'/missoes/argentina');
      assert.deepEqual(origins,[qa.base,qa.base]);
      await capture(page,'hoje',width);
      const identity=await page.evaluate(async()=>{const r=await fetch('/api/usuario');return r.json();});
      assert.equal(identity.permissoes.argentina.editar,true);
      assert.equal(identity.permissoes.portugal.editar,false);
      const denied=await page.goto(qa.base+'/missoes/portugal/atividades/nova');
      assert.equal(denied.status(),403);
      await capture(page,'acesso-negado',width);
      await page.getByRole('link',{name:/Voltar para Hoje/}).click();
      await page.waitForURL(qa.base+'/missoes/argentina');
      await page.goto(qa.base+'/missoes/argentina/planejamento?data=2026-11-18');
      await capture(page,'agenda',width);
      await page.goto(qa.base+'/missoes/argentina/atividades/nova');
      await capture(page,'formulario',width);
      await page.locator('.account-menu summary').click();
      await page.getByRole('button',{name:'Sair do aplicativo'}).click();
      await page.waitForURL(/login\?saiu=true/);
      assert.deepEqual(errors,[]);
      flows.push({width,recovery:true,postOriginPreserved:true,signedSyntheticLogin:true,missionPermission:true,logout:true,consoleErrors:0});
      await context.close();
    }
    const context=await browser.newContext({extraHTTPHeaders:qa.headers,viewport:{width:390,height:844},javaScriptEnabled:false});
    await context.route('https://accounts.google.com/**',route=>{
      const url=new URL(route.request().url());
      return route.fulfill({status:302,headers:{location:qa.base+'/__qa__/authorize?'+url.searchParams.toString()}});
    });
    const page=await context.newPage();page.setDefaultTimeout(10000);
    await page.goto(qa.base+'/login');
    await page.getByRole('button',{name:/Entrar com Google/}).click();
    await page.waitForURL(qa.base+'/missoes/argentina');
    await page.locator('.account-menu summary').click();
    await page.getByRole('button',{name:'Sair do aplicativo'}).click();
    await page.waitForURL(/login\?saiu=true/);
    await context.close();
    const report={layouts:layouts.length,results:layouts,flows,noJavaScript:true,googleAccountsUsed:false,database:'SQLite temporário com concessão validada',browser:await browser.version()};
    await fs.writeFile(path.join(output,'browser-report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({layouts:layouts.length,flows,noJavaScript:true,googleAccountsUsed:false}));
  } finally {
    if(qa)await qa.shutdown();
    await browser.close();
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
