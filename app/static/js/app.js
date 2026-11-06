"use strict";
// O conteúdo essencial e a navegação funcionam sem JavaScript.
document.querySelectorAll(".mission-switch").forEach((menu) => {
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      menu.open = false;
      menu.querySelector("summary").focus();
    }
  });
});
// A instalação e o service worker serão ativados em uma etapa futura.
// Nenhum dado, resposta da API ou documento é armazenado offline.
