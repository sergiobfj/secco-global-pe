"use strict";
// A preferência de missão é um cookie local do servidor, nunca autenticação.
document.addEventListener("click", (event) => {
  document.querySelectorAll(".mission-switch").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    document.querySelectorAll(".mission-switch[open]").forEach((menu) => {
      menu.open = false;
      menu.querySelector("summary").focus();
    });
  }
});
function showErrors(form, errors) {
  const summary = form.querySelector(".form-errors");
  summary.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = "Não foi possível salvar. Seus campos foram preservados.";
  const list = document.createElement("ul");
  Object.entries(errors).forEach(([field, message]) => {
    const li = document.createElement("li");
    li.textContent = message;
    list.append(li);
    const hint = [...form.querySelectorAll("[data-error-for]")].find(
      (node) => node.dataset.errorFor === field,
    );
    if (hint) hint.textContent = message;
    const input = form.elements.namedItem(field);
    if (input instanceof HTMLElement)
      input.setAttribute("aria-invalid", "true");
  });
  summary.append(title, list);
  if (errors.form && form.action.endsWith("/editar")) {
    const link = document.createElement("a");
    link.href = form.action.slice(0, -7);
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Conferir versão atual em outra aba";
    summary.append(link);
  }
  summary.hidden = false;
  const details = form.querySelector(".form-details");
  if (details) details.open = true;
  summary.focus();
}
document.addEventListener("input", (event) => {
  const form = event.target.closest("[data-activity-form]");
  if (!form) return;
  for (const input of form.querySelectorAll("input,select,textarea"))
    input.setCustomValidity("");
  event.target.removeAttribute("aria-invalid");
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (form.matches(".jump-date")) {
    event.preventDefault();
    if (form.reportValidity())
      loadAgenda(form.action + "?" + new URLSearchParams(new FormData(form)));
    return;
  }
  if (!form.matches("[data-activity-form]")) return;
  event.preventDefault();
  const fields = form.elements;
  if (fields.namedItem("titulo")) {
    const day = fields.namedItem("data");
    const start = fields.namedItem("horario_inicio");
    const end = fields.namedItem("horario_fim");
    const status = fields.namedItem("status");
    if (
      (!day.value && start.value) ||
      (!day.value && ["confirmado", "realizado"].includes(status.value))
    ) {
      day.setCustomValidity("Informe a data desta atividade.");
    }
    if (end.value && (!start.value || end.value <= start.value)) {
      end.setCustomValidity(
        "O término deve ser posterior ao início, no mesmo dia.",
      );
    }
  }
  if (!form.reportValidity()) return;
  const button = form.querySelector('button[type="submit"]');
  const feedback = form.querySelector(".form-feedback");
  button.disabled = true;
  form.setAttribute("aria-busy", "true");
  if (feedback) feedback.textContent = "Salvando no banco local...";
  form
    .querySelectorAll(".field-error")
    .forEach((node) => (node.textContent = ""));
  try {
    const response = await fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      body: new URLSearchParams(new FormData(form)),
    });
    const data = await response.json();
    if (!response.ok) {
      showErrors(
        form,
        data.errors || {
          form:
            typeof data.detail === "string"
              ? data.detail
              : "Não foi possível salvar. Confira os dados e tente novamente.",
        },
      );
      if (feedback) feedback.textContent = "Alterações não salvas.";
      return;
    }
    if (!data.redirect) throw new Error("Resposta inesperada");
    if (feedback) feedback.textContent = data.message;
    window.location.assign(data.redirect);
  } catch {
    showErrors(form, {
      form: "Sem conexão com o servidor local. Nada foi confirmado. Mantenha esta página aberta e tente novamente.",
    });
    if (feedback) feedback.textContent = "Alterações não salvas.";
  } finally {
    button.disabled = false;
    form.removeAttribute("aria-busy");
  }
});
function revealSelectedDay() {
  const selected = document.querySelector('.day-chip[aria-current="date"]');
  if (selected)
    selected.scrollIntoView({
      block: "nearest",
      inline: "center",
      behavior: "instant",
    });
}
let agendaController;
async function loadAgenda(url, push = true) {
  if (agendaController) agendaController.abort();
  const controller = new AbortController();
  agendaController = controller;
  const panel = document.querySelector("#planner-content");
  if (!panel) {
    window.location.assign(url);
    return;
  }
  const feedback = document.querySelector("#agenda-feedback");
  panel.setAttribute("aria-busy", "true");
  if (feedback) feedback.textContent = "Carregando agenda...";
  try {
    const response = await fetch(url, {
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error();
    const doc = new DOMParser().parseFromString(
      await response.text(),
      "text/html",
    );
    const updated = doc.querySelector("#planner-content");
    if (!updated) throw new Error();
    panel.replaceWith(updated);
    const focusTarget = [
      ...updated.querySelectorAll("a[data-agenda-link]"),
    ].find((link) => link.href === new URL(url, location.href).href);
    focusTarget?.focus({ preventScroll: true });
    if (push) history.pushState({ agenda: true }, "", url);
    revealSelectedDay();
    if (feedback) feedback.textContent = "Agenda atualizada.";
  } catch (error) {
    if (error.name === "AbortError") return;
    if (feedback)
      feedback.textContent =
        "Não foi possível carregar o dia. Confira a conexão e tente novamente.";
  } finally {
    if (agendaController === controller)
      document.querySelector("#planner-content")?.removeAttribute("aria-busy");
  }
}
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-agenda-link]");
  if (
    !link ||
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey ||
    event.altKey ||
    event.button !== 0
  )
    return;
  event.preventDefault();
  loadAgenda(link.href);
});
window.addEventListener("popstate", () => {
  if (document.querySelector("#planner-content"))
    loadAgenda(location.href, false);
});
revealSelectedDay();
// Não há upload, cache de dados, service worker ou sincronização nesta etapa.
