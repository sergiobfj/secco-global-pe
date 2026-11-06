/* Etapa 3: QA exclusivo em concessão temporária identificada. */
const { chromium } = require(process.argv[2] || "@playwright/test");
const { acquireQA } = require("./qa-guard.cjs");
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const output = path.resolve("artifacts/stage3");
(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.QA_BROWSER_PATH ||
      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    headless: true,
  });
  let qa;
  const results = [],
    flows = [];
  try {
    qa = await acquireQA(browser, process.env.QA_BASE_URL);
    await assert.rejects(() => acquireQA(browser, "http://127.0.0.1:8001"));
    await fs.mkdir(output, { recursive: true });
    const contexts = [];
    async function capture(page, name, width) {
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
          targets: [...document.querySelectorAll(".nav-item")].map(
            (el) => el.getBoundingClientRect().height,
          ),
        };
      });
      assert.ok(measure.scrollWidth <= width, JSON.stringify(measure));
      assert.deepEqual(measure.overflow, [], name + " " + width);
      assert.ok(
        measure.fonts && measure.targets.every((height) => height >= 44),
      );
      await page.screenshot({
        path: path.join(output, name + "-" + width + ".png"),
        fullPage: true,
      });
      results.push({ page: name, width, status: "aprovado", ...measure });
    }
    // Todas as capturas vazias e de contexto conhecido antecedem dados sintéticos.
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
        if (m.type() === "error") errors.push(m.text());
      });
      contexts.push({ context, page, width, errors });
      for (const [name, url] of [
        ["diario-vazio", "/missoes/argentina/diario"],
        ["hoje-argentina", "/missoes/argentina"],
        ["agenda-profissional", "/missoes/argentina/atividades/4"],
        ["formulario-vinculado", "/missoes/argentina/diario/novo?agenda=4"],
        ["formulario-manual", "/missoes/portugal/diario/novo"],
      ]) {
        const response = await page.goto(qa.base + url);
        assert.equal(response.status(), 200);
        await capture(page, name, width);
      }
      assert.deepEqual(errors, []);
    }
    for (const { context, page, width, errors } of contexts) {
      const title = "QA reunião profissional " + width + " " + Date.now();
      await page.goto(qa.base + "/missoes/argentina/atividades/nova");
      await page.getByLabel("Título obrigatório").fill(title);
      await page
        .getByLabel("Data opcional", { exact: true })
        .fill("2026-11-01");
      await page.getByLabel("Início opcional", { exact: true }).fill("10:00");
      await page
        .getByLabel("Status", { exact: true })
        .selectOption("confirmado");
      await page.locator(".form-details summary").click();
      await page
        .getByLabel("Organização envolvida", { exact: true })
        .fill("Organização exclusiva de QA");
      await page
        .getByLabel("Local", { exact: true })
        .fill("Local exclusivo de QA");
      await page.getByLabel("Tiago Prado", { exact: true }).check();
      await page.getByRole("button", { name: /Salvar atividade/ }).click();
      await page
        .getByText("Atividade salva no banco local.", { exact: true })
        .waitFor();
      const agendaURL = page.url().split("?")[0];
      await page.getByRole("link", { name: /Registrar resultado/ }).click();
      assert.equal(
        await page.getByLabel("Título", { exact: true }).inputValue(),
        title,
      );
      assert.equal(
        await page
          .getByLabel("Organização envolvida", { exact: true })
          .inputValue(),
        "Organização exclusiva de QA",
      );
      assert.equal(
        await page.getByLabel("Local", { exact: true }).inputValue(),
        "Local exclusivo de QA",
      );
      assert.equal(
        await page.getByLabel("Horário opcional", { exact: true }).inputValue(),
        "10:00",
      );
      assert.ok(
        await page.getByLabel("Tiago Prado", { exact: true }).isChecked(),
      );
      await page
        .getByLabel("Tipo de atividade", { exact: true })
        .selectOption("reuniao_empresarial");
      await page
        .getByLabel("Status do registro", { exact: true })
        .selectOption("realizada");
      await page
        .getByLabel("O que aconteceu", { exact: true })
        .fill("Descrição sintética exclusiva do teste isolado.");
      await page
        .getByLabel("Resultados obtidos", { exact: true })
        .fill("Resultado sintético, sem correspondência com reuniões reais.");
      await page.getByRole("button", { name: /Salvar registro/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      const recordURL = page.url().split("?")[0];
      await capture(page, "qa-registro-realizado", width);
      await page.goto(agendaURL);
      await page
        .getByRole("link", { name: /Abrir registro do Diário/ })
        .click();
      assert.equal(page.url(), recordURL);
      await page.reload();
      await page.getByRole("heading", { name: title, exact: true }).waitFor();

      await page.getByRole("link", { name: /Referenciar evidência/ }).click();
      await capture(page, "formulario-evidencia", width);
      await page
        .getByLabel("Título da evidência obrigatório", { exact: true })
        .fill("QA comprovação " + width);
      await page.getByRole("button", { name: /Salvar referência/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      assert.ok(
        (await page.locator(".diary-section").first().textContent()).includes(
          "Pendente",
        ),
      );
      await page.getByRole("link", { name: /Classificar resultado/ }).click();
      await capture(page, "formulario-classificacao", width);
      await page.getByRole("button", { name: /Salvar classificação/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      await page.getByText("Não contabilizado", { exact: true }).waitFor();

      await page
        .locator(".diary-section")
        .first()
        .getByRole("link", { name: "Revisar", exact: true })
        .click();
      await page
        .getByLabel("Situação da evidência", { exact: true })
        .selectOption("referencia_conferida");
      await page
        .getByLabel("Link HTTPS do documento existente", { exact: true })
        .fill("https://example.test/qa/" + width + "/" + Date.now());
      await page
        .getByLabel("Identificador único do documento", { exact: true })
        .fill("QA-" + width + "-" + Date.now());
      await page
        .getByLabel("Quem conferiu a referência", { exact: true })
        .fill("Responsável de QA");
      await page
        .getByLabel("O que foi conferido", { exact: true })
        .fill("Metadados sintéticos de teste, não comprovação operacional.");
      await page.getByRole("button", { name: /Salvar referência/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      await page
        .locator(".diary-section")
        .nth(1)
        .getByRole("link", { name: "Revisar", exact: true })
        .click();
      await page
        .getByLabel("Justificativa da classificação", { exact: true })
        .fill("Justificativa sintética para validar o mecanismo de contagem.");
      await page
        .getByLabel("Referência do critério ou orientação da coordenação", {
          exact: true,
        })
        .fill("Critério exclusivo do cenário de QA, sem aplicação às missões.");
      const proof = page
        .locator("#evidence_id option")
        .filter({ hasText: "QA comprovação " + width });
      await page
        .locator("#evidence_id")
        .selectOption(await proof.getAttribute("value"));
      await page
        .getByLabel("Decisão da coordenação", { exact: true })
        .selectOption("aprovada");
      await page
        .getByLabel("Responsável pela validação", { exact: true })
        .fill("Coordenação de QA");
      await page.getByRole("button", { name: /Salvar classificação/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      await page.getByText("Contabilizado na meta", { exact: true }).waitFor();
      const goals = await context.request.get(
        qa.base + "/api/missoes/argentina",
      );
      assert.equal(
        (await goals.json()).metas.find(
          (g) => g.tipo_meta === "reuniao_qualificada",
        ).realizado,
        1,
      );
      await page.goto(qa.base + "/missoes/argentina");
      assert.ok(
        (await page.locator(".metric-number").first().textContent()).includes(
          "01",
        ),
      );
      await capture(page, "qa-dashboard-resultados", width);
      await page.goto(recordURL + "/editar");
      await page
        .getByLabel("Status do registro", { exact: true })
        .selectOption("cancelada");
      await page.getByRole("button", { name: /Salvar registro/ }).click();
      await page
        .getByText("Registro salvo no banco local.", { exact: true })
        .waitFor();
      const revoked = await context.request.get(
        qa.base + "/api/missoes/argentina",
      );
      assert.equal(
        (await revoked.json()).metas.find(
          (g) => g.tipo_meta === "reuniao_qualificada",
        ).realizado,
        0,
      );
      assert.deepEqual(errors, [], "Console " + width);
      flows.push({
        width,
        prefill: true,
        create: true,
        evidence: true,
        approval: true,
        revocation: true,
        consoleErrors: 0,
      });
      await context.close();
    }

    const noJS = await browser.newContext({
      extraHTTPHeaders: qa.headers,
      javaScriptEnabled: false,
      viewport: { width: 390, height: 844 },
    });
    const p = await noJS.newPage();
    await p.goto(qa.base + "/missoes/portugal/diario/novo");
    await p
      .getByLabel("Título", { exact: true })
      .fill("QA rascunho sem JavaScript");
    await p.getByLabel("Data local", { exact: true }).fill("");
    await p.getByRole("button", { name: /Salvar registro/ }).click();
    await p
      .getByText("Registro salvo no banco local.", { exact: true })
      .waitFor();
    await p.getByRole("link", { name: /Completar rascunho/ }).click();
    await p
      .getByLabel("Status do registro", { exact: true })
      .selectOption("realizada");
    await p.getByRole("button", { name: /Salvar registro/ }).click();
    await p.getByRole("alert").waitFor();
    assert.equal(
      await p.getByLabel("Título", { exact: true }).inputValue(),
      "QA rascunho sem JavaScript",
    );
    await noJS.close();

    const keyboard = await browser.newContext({
      extraHTTPHeaders: qa.headers,
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
    });
    const k = await keyboard.newPage();
    await k.goto(qa.base + "/missoes/argentina/diario/novo");
    await k.keyboard.press("Tab");
    assert.equal(
      await k.evaluate(() => document.activeElement.textContent),
      "Ir para o conteúdo",
    );
    await k.keyboard.press("Enter");
    assert.equal(await k.evaluate(() => document.activeElement.id), "conteudo");
    await k
      .getByLabel("Título", { exact: true })
      .fill("QA texto preservado em falha de conexão");
    await k.route("**/diario/novo", (r) =>
      r.request().method() === "POST" ? r.abort() : r.continue(),
    );
    await k.getByRole("button", { name: /Salvar registro/ }).click();
    await k.getByText(/Sem conexão com o servidor local/).waitFor();
    assert.equal(
      await k.getByLabel("Título", { exact: true }).inputValue(),
      "QA texto preservado em falha de conexão",
    );
    await k.unroute("**/diario/novo");
    await k
      .getByLabel("Status do registro", { exact: true })
      .selectOption("realizada");
    await k.getByRole("button", { name: /Salvar registro/ }).click();
    assert.equal(
      await k
        .getByLabel("Resultados obtidos", { exact: true })
        .getAttribute("required"),
      "",
    );
    await k
      .getByLabel("Status do registro", { exact: true })
      .selectOption("rascunho");
    await k.getByRole("button", { name: /Salvar registro/ }).click();
    await k
      .getByText("Registro salvo no banco local.", { exact: true })
      .waitFor();
    await keyboard.close();
    const report = {
      date: new Date().toISOString(),
      browser: await browser.version(),
      policy: "temporary-lease-v1",
      layouts: results.length,
      results,
      flows,
      noJavaScript: true,
      keyboard: true,
      networkFailurePreservesText: true,
      operationalServerRefused: true,
      dataset:
        "Somente concessão temporária. Telas com prefixo qa usam registros sintéticos identificados.",
    };
    await fs.writeFile(
      path.join(output, "report.json"),
      JSON.stringify(report, null, 2),
    );
    console.log(
      JSON.stringify(
        {
          layouts: results.length,
          flows,
          widths: [360, 390, 768, 1280],
          noJavaScript: true,
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
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
