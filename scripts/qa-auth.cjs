/* Teste de navegador: OIDC sintético assinado, nunca Google ou banco operacional. */
const { chromium } = require(process.argv[2] || "@playwright/test");
const { acquireQA } = require("./qa-guard.cjs");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const output = path.resolve("artifacts/stage4");
const pending = process.argv.includes("--pending");
(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.QA_BROWSER_PATH ||
      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    headless: true,
  });
  let qa;
  const layouts = [],
    flows = [];
  try {
    qa = await acquireQA(browser, process.env.QA_BASE_URL);
    assert.equal(qa.authMode, pending ? "pending" : "synthetic");
    await assert.rejects(() => acquireQA(browser, "http://127.0.0.1:8003"));
    await fs.mkdir(output, { recursive: true });
    async function capture(page, name, width) {
      await page.evaluate(() => document.fonts.ready);
      const measure = await page.evaluate(() => ({
        width: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        overflow: [...document.querySelectorAll("main *")]
          .filter((el) => {
            if (el.closest(".day-strip")) return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && (r.left < -1 || r.right > innerWidth + 1);
          })
          .map((el) => el.tagName + "." + el.className),
        fonts:
          document.fonts.check('16px "Manrope"') &&
          document.fonts.check('16px "Space Grotesk"'),
      }));
      assert.ok(measure.scrollWidth <= width, JSON.stringify(measure));
      assert.deepEqual(measure.overflow, [], name + " " + width);
      assert.ok(measure.fonts);
      await page.screenshot({
        path: path.join(output, name + "-" + width + ".png"),
        fullPage: true,
      });
      layouts.push({ page: name, width, ...measure });
    }
    async function browserAPI(page, url, method = "GET", form = null) {
      return page.evaluate(
        async ({ url, method, form }) => {
          const response = await fetch(url, {
            method,
            credentials: "same-origin",
            headers: { Accept: "application/json" },
            ...(form ? { body: new URLSearchParams(form) } : {}),
          });
          return { status: response.status, json: await response.json() };
        },
        { url, method, form },
      );
    }
    async function mockGoogle(context) {
      await context.route(
        "https://accounts.google.com/o/oauth2/v2/auth**",
        async (route) => {
          const url = new URL(route.request().url());
          assert.equal(url.searchParams.get("scope"), "openid email");
          assert.equal(url.searchParams.get("code_challenge_method"), "S256");
          await route.fulfill({
            status: 302,
            headers: {
              location:
                qa.base + "/__qa__/authorize?" + url.searchParams.toString(),
            },
          });
        },
      );
    }
    for (const width of [360, 390, 768, 1280]) {
      const context = await browser.newContext({
        extraHTTPHeaders: qa.headers,
        viewport: { width, height: 900 },
        locale: "pt-BR",
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("console", (m) => {
        if (
          m.type() === "error" &&
          !m.text().includes("503") &&
          !m.text().includes("403") &&
          !m.text().includes("401")
        )
          errors.push(m.text());
      });
      if (pending) {
        const response = await page.goto(qa.base + "/");
        assert.equal(response.status(), 503);
        await page
          .getByRole("heading", { name: "Acesse sua missão." })
          .waitFor();
        assert.ok(
          await page
            .getByRole("button", { name: /Entrar com Google/ })
            .isDisabled(),
        );
        await capture(page, "login-pendente", width);
        flows.push({ width, failClosed: true });
        await context.close();
        continue;
      }
      await mockGoogle(context);
      await page.goto(qa.base + "/");
      await capture(page, "login", width);
      await page.getByRole("button", { name: /Entrar com Google/ }).click();
      await page.waitForURL(qa.base + "/missoes/argentina");
      await capture(page, "hoje-autenticado", width);
      const userResponse = await browserAPI(page, "/api/usuario");
      assert.equal(userResponse.status, 200);
      const user = userResponse.json;
      assert.equal(user.participant_id, 3);
      assert.equal(user.permissoes.argentina.editar, true);
      assert.equal(user.permissoes.portugal.editar, false);
      await page.locator(".account-menu summary").click();
      await page.getByText("Tiago Prado", { exact: true }).first().waitFor();
      await capture(page, "conta", width);
      await page.keyboard.press("Escape");
      assert.equal(
        await page.locator(".account-menu").getAttribute("open"),
        null,
      );
      await page.goto(
        qa.base + "/missoes/argentina/planejamento?data=2026-11-18",
      );
      await capture(page, "agenda-autenticada", width);
      await page.goto(qa.base + "/missoes/argentina/diario");
      await capture(page, "diario-autenticado", width);
      await page.goto(qa.base + "/missoes/portugal/planejamento");
      await capture(page, "consulta-outra-missao", width);
      assert.equal(
        await page.getByRole("link", { name: /Nova atividade/ }).count(),
        0,
      );
      const csrf = await page
        .locator('input[name="csrf_token"]')
        .first()
        .inputValue();
      const denied = await browserAPI(
        page,
        "/missoes/portugal/diario/novo",
        "POST",
        { csrf_token: csrf },
      );
      assert.equal(denied.status, 403);

      const blocked = await page.goto(
        qa.base + "/missoes/portugal/atividades/nova",
      );
      assert.equal(blocked.status(), 403);
      await capture(page, "acesso-negado", width);
      await page.goto(qa.base + "/missoes/argentina/diario/novo");
      await page
        .getByLabel("Título", { exact: true })
        .fill("QA atividade autenticada " + width);
      await page
        .getByLabel("Status do registro", { exact: true })
        .selectOption("realizada");
      await page
        .getByLabel("O que aconteceu", { exact: true })
        .fill("Registro sintético em banco temporário.");
      await page
        .getByLabel("Resultados obtidos", { exact: true })
        .fill("Resultado sintético para verificar autoria.");
      await page.getByRole("button", { name: /Salvar registro/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      await page.getByText(/Criado por Tiago Prado/).waitFor();
      await capture(page, "qa-registro-com-autoria", width);
      await page.locator(".account-menu summary").click();
      await page.getByRole("button", { name: "Sair do aplicativo" }).click();
      await page.waitForURL(/login\?saiu=true/);
      assert.equal((await browserAPI(page, "/api/usuario")).status, 401);
      assert.deepEqual(errors, [], "Console " + width);
      flows.push({
        width,
        login: true,
        defaultMission: true,
        readOnlyCrossMission: true,
        backendDenied: true,
        diaryAuthor: true,
        logout: true,
        consoleErrors: 0,
      });
      await context.close();
    }
    if (!pending) {
      const context = await browser.newContext({
        extraHTTPHeaders: qa.headers,
        javaScriptEnabled: false,
        viewport: { width: 390, height: 844 },
      });
      await mockGoogle(context);
      const page = await context.newPage();
      await page.goto(qa.base + "/login");
      await page.keyboard.press("Tab");
      assert.equal(
        await page.evaluate(() => document.activeElement.textContent),
        "Ir para o conteúdo",
      );
      await page.getByRole("button", { name: /Entrar com Google/ }).click();
      await page.waitForURL(qa.base + "/missoes/argentina");
      await page.locator(".account-menu summary").click();
      await page.getByRole("button", { name: "Sair do aplicativo" }).click();
      await page.waitForURL(/login\?saiu=true/);
      await context.close();
    }
    const report = {
      date: new Date().toISOString(),
      browser: await browser.version(),
      mode: qa.authMode,
      layouts: layouts.length,
      results: layouts,
      flows,
      noJavaScript: !pending,
      googleAccountsUsed: false,
      database: "Concessão temporária verificada",
      dependencyValidation:
        "Pacotes de teste em cache; pins de runtime pendentes de instalação",
    };
    await fs.writeFile(
      path.join(output, pending ? "report-pending.json" : "report-auth.json"),
      JSON.stringify(report, null, 2),
    );
    console.log(
      JSON.stringify(
        { mode: qa.authMode, layouts: layouts.length, flows },
        null,
        2,
      ),
    );
  } finally {
    if (qa) await qa.shutdown();
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
