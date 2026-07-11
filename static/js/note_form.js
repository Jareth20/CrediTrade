(() => {
  const clientSelect = document.getElementById('id_cliente_vendedor');
  const panel = document.getElementById('historical-suggestions');
  const content = document.getElementById('historical-content');
  if (!clientSelect || !panel || !content) return;

  const fieldMap = {
    tipo_nota: 'id_tipo_nota',
    origen_tributario: 'id_origen_tributario',
    valor_nominal: 'id_valor_nominal',
    saldo_disponible: 'id_saldo_disponible',
    minimo_recibir: 'id_minimo_recibir'
  };

  const escapeHtml = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  function applyHistorical(record) {
    Object.entries(fieldMap).forEach(([key, id]) => {
      const element = document.getElementById(id);
      if (element && record[key] !== undefined && record[key] !== null) {
        element.value = record[key];
        element.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    const button = content.querySelector('[data-apply-latest]');
    if (button) {
      button.innerHTML = '<i class="bi bi-check-lg me-1"></i>Aplicado para revisión';
      button.classList.replace('btn-outline-primary', 'btn-success');
    }
  }

  async function loadHistory() {
    const clientId = clientSelect.value;
    if (!clientId) {
      panel.classList.add('d-none');
      content.innerHTML = '';
      return;
    }
    panel.classList.remove('d-none');
    content.innerHTML = '<div class="small text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Buscando antecedentes...</div>';
    try {
      const response = await fetch(`/api/clientes/buscar/?cliente_id=${encodeURIComponent(clientId)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!response.ok) throw new Error('No se pudo consultar');
      const data = await response.json();
      if (!data.found) {
        content.innerHTML = '<div class="small text-muted">No se encontró el cliente.</div>';
        return;
      }
      if (!data.antecedentes.length) {
        content.innerHTML = `<div class="small"><strong>${escapeHtml(data.cliente.nombre)}</strong><br><span class="text-muted">Sin notas anteriores para reutilizar.</span></div>`;
        return;
      }
      const latest = data.antecedentes[0];
      content.innerHTML = `
        <div class="small mb-3">
          <strong>${escapeHtml(data.cliente.nombre)}</strong><br>
          <span class="text-muted">${escapeHtml(data.cliente.ruc)} · ${data.antecedentes.length} antecedente(s)</span>
        </div>
        <div class="historical-item mb-3">
          <div class="fw-semibold">Último: ${escapeHtml(latest.numero_titulo)}</div>
          <div class="small text-muted">Nominal $${escapeHtml(latest.valor_nominal)} · Saldo $${escapeHtml(latest.saldo_disponible)}</div>
        </div>
        <button type="button" class="btn btn-sm btn-outline-primary w-100" data-apply-latest>
          <i class="bi bi-arrow-down-square me-1"></i>Prellenar con último antecedente
        </button>
        <div class="tiny text-muted mt-2">No se guarda hasta que envíes el formulario. Después podrás generar sugerencias de Gemini y revisar cada campo.</div>`;
      content.querySelector('[data-apply-latest]').addEventListener('click', () => applyHistorical(latest));
    } catch (error) {
      content.innerHTML = '<div class="small text-danger">No se pudo cargar el historial. Puedes continuar manualmente.</div>';
    }
  }

  clientSelect.addEventListener('change', loadHistory);
  if (clientSelect.value) loadHistory();
})();
