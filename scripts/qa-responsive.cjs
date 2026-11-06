/* QA local da etapa 2. Execute contra um banco exclusivo de testes.
 * node scripts/qa-responsive.cjs [caminho absoluto de @playwright/test]
 */
const { chromium } = require(process.argv[2] || "@playwright/test");
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { acquireQA } = require("./qa-guard.cjs");
const output = path.resolve("artifacts/stage2");
(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.QA_BROWSER_PATH ||
      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    headless: true,
  });
  await fs.mkdir(output, { recursive: true });
  const results = [];
  let qa;
  let base;
  try {
    qa = await acquireQA(browser, process.env.QA_BASE_URL);
    base = qa.base;
    for (const width of [360, 390, 768, 1280]) {
      const context = await browser.newContext({
        extraHTTPHeaders: qa.headers,
        viewport: { width, height: 900 },
        locale: "pt-BR",
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(m.text());
      });
      const routes = [
        ["selecao", "/?selecionar=1"],
        ["hoje-portugal", "/missoes/portugal"],
        ["hoje-argentina", "/missoes/argentina"],
        ["agenda-argentina", "/missoes/argentina/planejamento?data=2026-11-18"],
        ["sem-data-portugal", "/missoes/portugal/planejamento?sem_data=true"],
        ["detalhes", "/missoes/argentina/atividades/1"],
        ["nova-atividade", "/missoes/argentina/atividades/nova"],
        ["editar-atividade", "/missoes/argentina/atividades/1/editar"],
      ];
      for (const [name, url] of routes) {
        const response = await page.goto(base + url);
        assert.equal(response.status(), 200, url);
        await page.evaluate(() => document.fonts.ready);
        const measure = await page.evaluate(() => {
          const overflow = [...document.querySelectorAll("main *")]
            .filter((el) => {
              if (el.closest(".day-strip")) return false;
              const r = el.getBoundingClientRect();
              return r.width > 0 && (r.left < -1 || r.right > innerWidth + 1);
            })
            .map((el) => el.tagName + "." + el.className);
          return {
            width: innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            overflow,
            fonts:
              document.fonts.check('16px "Manrope"') &&
              document.fonts.check('16px "Space Grotesk"'),
            nav: [...document.querySelectorAll(".nav-item")].map(
              (el) => el.getBoundingClientRect().height,
            ),
            logo: [...document.querySelectorAll(".official-logo,.header-logo")]
              .filter((el) => el.getBoundingClientRect().width)
              .every(
                (el) =>
                  el.naturalWidth > 0 &&
                  Math.abs(
                    el.getBoundingClientRect().width /
                      el.getBoundingClientRect().height -
                      1640.262 / 288.7464,
                  ) < 0.1,
              ),
          };
        });
        assert.ok(measure.scrollWidth <= width, JSON.stringify(measure));
        assert.deepEqual(measure.overflow, [], name + " " + width);
        assert.ok(
          measure.fonts && measure.logo,
          "Fontes e proporções oficiais",
        );
        assert.ok(measure.nav.every((height) => height >= 44));
        await page.screenshot({
          path: path.join(output, name + "-" + width + ".png"),
          fullPage: true,
        });
        results.push({ page: name, width, status: "aprovado", ...measure });
      }
      await page.goto(base + "/?selecionar=1");
      await page.getByRole("link", { name: "Acessar missão" }).last().click();
      assert.ok(page.url().endsWith("/missoes/argentina"));
      await page.goto(base + "/");
      assert.ok(page.url().endsWith("/missoes/argentina"), "Missão lembrada");
      await page.locator(".mission-switch summary").click();
      await page
        .locator(".switch-menu")
        .getByRole("link", { name: "Portugal", exact: true })
        .click();
      await page.goto(base + "/");
      assert.ok(page.url().endsWith("/missoes/portugal"));
      await page.goto(base + "/missoes/argentina/planejamento?data=2026-11-18");
      const firstHandle = await page.locator(".sidebar").elementHandle();
      await page.locator('.day-chip[href$="2026-11-19"]').click();
      await page.waitForURL(/data=2026-11-19/);
      await page
        .getByRole("heading", { name: "19/11/2026", exact: true })
        .waitFor();
      assert.ok(
        await firstHandle.evaluate((el) => el.isConnected),
        "Troca de dia sem recarregar o shell",
      );
      await page.goBack();
      await page
        .getByRole("heading", { name: "18/11/2026", exact: true })
        .waitFor();

      // Dados sintéticos somente no banco de QA, nunca no banco de uso.
      const title = "QA atividade " + width + " " + Date.now();
      await page.goto(base + "/missoes/argentina/atividades/nova");
      await page.getByLabel("Título obrigatório").fill(title);
      await page.getByRole("button", { name: /Salvar atividade/ }).click();
      await page
        .getByText("Atividade salva no banco local.", { exact: true })
        .waitFor();
      const activityURL = page.url().split("?")[0];
      await page.reload();
      await page.getByRole("heading", { name: title, exact: true }).waitFor();
      await page.getByRole("link", { name: /Editar atividade/ }).click();
      await page
        .getByLabel("Status", { exact: true })
        .selectOption("confirmado");
      await page
        .getByLabel("Data opcional", { exact: true })
        .fill("2026-11-18");
      await page.getByLabel("Início opcional", { exact: true }).fill("10:00");
      await page.getByLabel("Término opcional", { exact: true }).fill("11:00");
      await page.locator(".form-details summary").click();
      await page
        .getByLabel("Local", { exact: true })
        .fill("Local exclusivo de QA");
      await page
        .getByLabel("Endereço", { exact: true })
        .fill("Endereço de teste, Buenos Aires");
      await page.getByLabel(/Endereço conferido/).check();
      await page.getByLabel("Tiago Prado", { exact: true }).check();
      await page.getByRole("button", { name: /Salvar atividade/ }).click();
      await page
        .getByText("Atividade salva no banco local.", { exact: true })
        .waitFor();
      assert.ok(
        (
          await page
            .getByRole("link", { name: /Como chegar/ })
            .getAttribute("href")
        ).includes("api=1"),
      );
      await page.goto(base + "/missoes/argentina");
      await page
        .locator(".up-next")
        .getByRole("heading", { name: title, exact: true })
        .waitFor();
      await page.goto(activityURL);
      await page.locator(".cancel-section summary").click();
      await page
        .getByRole("button", { name: "Confirmar cancelamento", exact: true })
        .click();
      await page
        .getByText("Atividade cancelada. O histórico foi preservado.", {
          exact: true,
        })
        .waitFor();
      await page.locator(".detail-heading .status-cancelado").waitFor();
      assert.deepEqual(errors, [], "Erros de console");
      await context.close();
    }

    const context = await browser.newContext({
      extraHTTPHeaders: qa.headers,
      viewport: { width: 390, height: 844 },
      javaScriptEnabled: false,
    });
    const page = await context.newPage();
    await page.goto(base + "/?selecionar=1");
    await page.getByRole("link", { name: "Acessar missão" }).first().click();
    await page.goto(base + "/");
    assert.ok(page.url().endsWith("/missoes/portugal"));
    await page.locator(".nav-item").nth(1).click();
    await page.getByRole("link", { name: /Nova atividade/ }).click();
    await page.getByLabel("Título obrigatório").fill("QA sem JavaScript");
    await page.getByRole("button", { name: /Salvar atividade/ }).click();
    await page
      .getByText("Atividade salva no banco local.", { exact: true })
      .waitFor();
    await page.getByRole("link", { name: /Editar atividade/ }).click();
    await page.getByLabel("Status", { exact: true }).selectOption("confirmado");
    await page.getByLabel("Data opcional", { exact: true }).fill("");
    await page.getByRole("button", { name: /Salvar atividade/ }).click();
    await page
      .getByText("Atividades confirmadas ou realizadas precisam de data.", {
        exact: false,
      })
      .first()
      .waitFor();
    assert.equal(
      await page.getByLabel("Título obrigatório").inputValue(),
      "QA sem JavaScript",
    );
    await context.close();

    const keyboard = await browser.newContext({
      extraHTTPHeaders: qa.headers,
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
    });
    const keyPage = await keyboard.newPage();
    await keyPage.goto(base + "/?selecionar=1");
    await keyPage.keyboard.press("Tab");
    assert.equal(
      await keyPage.evaluate(() => document.activeElement.textContent),
      "Ir para o conteúdo",
    );
    await keyPage.keyboard.press("Enter");
    assert.equal(
      await keyPage.evaluate(() => document.activeElement.id),
      "conteudo",
    );
    await keyPage.goto(base + "/missoes/argentina");
    await keyPage.locator(".mission-switch summary").focus();
    await keyPage.keyboard.press("Enter");
    assert.notEqual(
      await keyPage.locator(".mission-switch").getAttribute("open"),
      null,
    );
    await keyPage.keyboard.press("Escape");
    assert.equal(
      await keyPage.locator(".mission-switch").getAttribute("open"),
      null,
    );
    await keyPage.goto(base + "/missoes/argentina/atividades/nova");
    await keyPage
      .getByLabel("Título obrigatório")
      .fill("Campos preservados sem servidor");
    await keyPage.route("**/atividades/nova", (route) =>
      route.request().method() === "POST" ? route.abort() : route.continue(),
    );
    await keyPage.getByRole("button", { name: /Salvar atividade/ }).click();
    await keyPage.getByText(/Sem conexão com o servidor local/).waitFor();
    assert.equal(
      await keyPage.getByLabel("Título obrigatório").inputValue(),
      "Campos preservados sem servidor",
    );
    await keyboard.close();
    const report = {
      date: new Date().toISOString(),
      browser: await browser.version(),
      layouts: results.length,
      results,
      flows: [
        "Missão padrão no servidor",
        "Troca de missão",
        "Troca de dia sem reload do shell",
        "Criação",
        "Edição",
        "Persistência",
        "Mapa por endereço",
        "Cancelamento",
        "Sem JavaScript",
        "Validação preservando dados",
        "Falha de rede sem confirmação falsa",
        "Teclado e Escape",
      ],
      database: "Banco exclusivo de QA",
    };
    await fs.writeFile(
      path.join(output, "report.json"),
      JSON.stringify(report, null, 2),
    );
    console.log(
      JSON.stringify(
        {
          layouts: results.length,
          widths: [360, 390, 768, 1280],
          flows: report.flows,
          errors: 0,
          report: path.join(output, "report.json"),
        },
        null,
        2,
      ),
    );
  } finally {
    if (qa) await qa.shutdown();
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
