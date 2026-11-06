"use strict";
(() => {
  const form = document.querySelector('[data-receipt-form]');
  if (!form) return;
  const type = form.elements.namedItem('tipo');
  const summary = form.querySelector('.receipt-errors');
  const feedback = form.querySelector('.receipt-feedback');
  const preview = form.querySelector('.receipt-preview');
  let urls = [];
  let pending = false;
  function showErrors(messages) {
    summary.replaceChildren();
    const title = document.createElement('strong');
    title.textContent = 'Confira antes de salvar. Seus campos e arquivos foram preservados.';
    const list = document.createElement('ul');
    Object.values(messages).forEach(message => {const li = document.createElement('li');li.textContent = message;list.append(li);});
    summary.append(title,list); summary.hidden = false; summary.focus();
  }
  function syncType() {
    form.querySelectorAll('[data-checklist]').forEach(section => {
      const active = section.dataset.checklist === type.value;
      section.hidden = !active; section.open = active;
      section.querySelectorAll('input,select').forEach(input => {input.disabled = !active;});
    });
  }
  syncType();
  type.addEventListener('change',syncType);
  function showPreview() {
    urls.forEach(url => URL.revokeObjectURL(url)); urls = []; preview.replaceChildren();
    const files = [...form.elements.namedItem('camera').files,...form.elements.namedItem('files').files];
    if (files.length > 4 || files.some(file => file.size > 5*1024*1024)) {
      showErrors({files:'Use até 4 arquivos por envio e até 5 MB por arquivo.'});
    }
    files.forEach(file => {
      const figure = document.createElement('figure');
      const caption = document.createElement('figcaption');
      caption.textContent = file.name+' · '+(file.size/1024).toFixed(0)+' KB';
      if (['image/png','image/jpeg'].includes(file.type)) {
        const url = URL.createObjectURL(file); urls.push(url);
        const img = document.createElement('img'); img.src = url; img.alt = 'Prévia do comprovante sintético selecionado';figure.append(img);
      } else if (file.type === 'application/pdf') {
        const url = URL.createObjectURL(file); urls.push(url);
        const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';link.textContent = 'Visualizar PDF em outra aba';figure.append(link);
      }
      figure.append(caption); preview.append(figure);
    });
  }
  form.querySelectorAll('input[type=file]').forEach(input => input.addEventListener('change',showPreview));
  window.addEventListener('beforeunload',event => {if(pending){event.preventDefault();event.returnValue='';}});
  form.addEventListener('submit',async event => {
    event.preventDefault();
    if (pending || !form.reportValidity()) return;
    const files = [...form.elements.namedItem('camera').files,...form.elements.namedItem('files').files];
    if (files.length > 4 || files.some(file => file.size > 5*1024*1024)) {showErrors({files:'Use até 4 arquivos por envio e até 5 MB por arquivo.'});return;}
    const body = new FormData(form);
    const button = form.querySelector('button[type=submit]');
    pending = true; button.disabled = true; feedback.textContent = 'Enviando. Aguarde a confirmação do servidor.';summary.hidden = true;
    try {
      const response = await fetch(form.action,{method:'POST',body,headers:{Accept:'application/json'},credentials:'same-origin'});
      const result = await response.json();
      if (!response.ok) {showErrors(result.errors || {form:result.detail || 'Não foi possível confirmar o recebimento.'});feedback.textContent = 'Envio não confirmado.';return;}
      if (!result.redirect) throw new Error('Confirmação ausente');
      pending = false; location.assign(result.redirect);
    } catch (_) {
      showErrors({form:'Não foi possível confirmar o salvamento. Seus campos e arquivos continuam aqui. Reenvie o mesmo formulário para evitar duplicação.'});
      feedback.textContent = 'Envio não confirmado.';
    } finally {pending = false;button.disabled = false;}
  });
})();
