const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");

async function acquireQA(browser, override) {
  let manifest;
  for(let attempt=0;attempt<25;attempt++){
    try{manifest=JSON.parse(await fs.readFile(path.resolve(__dirname,"../.tools/qa-current.json"),"utf8"));break;}
    catch(error){if(error.code!=="ENOENT"||attempt===24)throw error;await new Promise(resolve=>setTimeout(resolve,200));}
  }
  const url = new URL(manifest.url);
  assert.ok(
    url.protocol === "http:" &&
      ["127.0.0.1", "localhost"].includes(url.hostname),
    "QA somente em loopback.",
  );
  assert.ok(
    !["8000", "8001", "8002", "8003"].includes(url.port),
    "Porta operacional recusada pelo cliente de QA.",
  );
  if (override)
    assert.equal(
      override.replace(/\/$/, ""),
      manifest.url,
      "A URL precisa corresponder ao servidor temporário iniciado nesta execução.",
    );
  const headers = { "X-SECCO-QA-Instance": manifest.instance };
  const context = await browser.newContext({ extraHTTPHeaders: headers });
  let response;
  try {
    for (let attempt=0; attempt<25; attempt++) {
      try { response=await context.request.get(manifest.url+"/__qa__/identity"); break; }
      catch(error) { if(attempt===24 || !/ECONNREFUSED|ECONNRESET/.test(error.message)) throw error; await new Promise(resolve=>setTimeout(resolve,200)); }
    }
  } catch(error) { await context.close(); throw error; }
  assert.equal(
    response.status(),
    200,
    "Servidor sem identidade de teste temporário.",
  );
  assert.deepEqual(await response.json(), {
    qa: true,
    isolated: true,
    policy: "temporary-lease-v1",
    instance: manifest.instance,
  });
  await context.close();
  return {
    base: manifest.url,
    authMode: manifest.auth_mode,
    headers,
    async shutdown() {
      const client = await browser.newContext({ extraHTTPHeaders: headers });
      await client.request.get(manifest.url + "/?selecionar=1");
      const token = (await client.cookies(manifest.url)).find(
        (c) => c.name === "secco_csrf",
      )?.value;
      if (token)
        await client.request.post(manifest.url + "/__qa__/shutdown", {
          form: { csrf_token: token },
        });
      await client.close();
    },
  };
}
module.exports = { acquireQA };
