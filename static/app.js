const state = { services: [], timer: null, revenueChart: null, platformChart: null };
const $ = (selector) => document.querySelector(selector);
const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value || 0);
let adminKey = sessionStorage.getItem("orbit_admin_key") || "";

function askAdminKey() {
  if (adminKey) return adminKey;
  const entered = window.prompt("Informe a chave administrativa para acessar o painel:");
  if (entered) {
    adminKey = entered.trim();
    sessionStorage.setItem("orbit_admin_key", adminKey);
  }
  return adminKey;
}

async function api(path, options = {}) {
  const { _retry, ...requestOptions } = options;
  const headers = { "Content-Type": "application/json", ...(adminKey ? { "X-Admin-Key": adminKey } : {}), ...(requestOptions.headers || {}) };
  let response = await fetch(path, { ...requestOptions, headers });
  if (response.status === 401 && !_retry) {
    askAdminKey();
    response = await fetch(path, { ...requestOptions, headers: { ...headers, ...(adminKey ? { "X-Admin-Key": adminKey } : {}) } });
  }
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Não foi possível concluir a operação.");
  return payload;
}

async function loadServices() {
  try {
    const response = await api("/api/catalogo");
    if (!response.sucesso) throw new Error(response.erro || "Erro ao carregar catálogo.");
    state.services = response.servicos || [];
    if (!state.services.length) throw new Error("O fornecedor não retornou serviços.");
    renderCatalog();
    updateServiceOptions();
    updateEstimate();
  } catch (error) {
    state.services = [];
    $("#catalog-grid").innerHTML = `<div class="catalog-alert"><strong>Nenhuma API SMM configurada ou erro de conexão com o fornecedor.</strong><span>${error.message}</span><button class="primary-button" id="go-settings" type="button">Ir para Configurações</button></div>`;
    $("#service").innerHTML = `<option value="">Configure o fornecedor primeiro</option>`;
    $("#go-settings").addEventListener("click", () => $("#settings").scrollIntoView({ behavior: "smooth" }));
    updateEstimate();
  }
}

function serviceId() {
  return $("#service").value;
}

function isCommentsService() {
  return $("#service-type").value === "comentarios";
}

function updateEstimate() {
  const service = state.services.find((item) => item.service_id === serviceId());
  const quantity = isCommentsService()
    ? $("#comentarios-input").value.split("\n").filter((line) => line.trim()).length
    : Number($("#quantity").value) || 0;
  const cost = service ? service.rate_per_thousand * quantity / 1000 : 0;
  const customer = service ? service.preco_venda * quantity / 1000 : 0;
  $("#provider-price").textContent = money(cost);
  $("#customer-price").textContent = money(customer);
  $("#profit-price").textContent = money(customer - cost);
}

function updateServiceOptions() {
  const platform = $("#platform").value.toLowerCase();
  const type = $("#service-type").value;
  const matches = state.services.filter((item) => {
    const text = `${item.name} ${item.category}`.toLowerCase();
    const typeMatches = type === "comentarios" ? item.type === "custom_comments" || text.includes("comment") || text.includes("coment") : type === "curtidas" ? text.includes("like") || text.includes("curtida") : type === "visualizacoes" ? text.includes("view") || text.includes("visualiza") : text.includes("follower") || text.includes("subscriber") || text.includes("segu") || text.includes("inscri");
    return item.platform.toLowerCase().includes(platform) && typeMatches;
  });
  const options = (matches.length ? matches : state.services.filter((item) => item.platform.toLowerCase().includes(platform))).map((item) => `<option value="${item.service_id}">${item.name} · R$ ${item.rate_fornecedor.toFixed(2)}/1k</option>`);
  $("#service").innerHTML = options.join("") || `<option value="">Nenhum serviço encontrado</option>`;
  updateEstimate();
}

function renderCatalog() {
  const search = $("#catalog-search").value.toLowerCase();
  const platform = $("#catalog-platform").value.toLowerCase();
  const items = state.services.filter((item) => (!search || `${item.name} ${item.category}`.toLowerCase().includes(search)) && (!platform || `${item.platform} ${item.category} ${item.name}`.toLowerCase().includes(platform)));
  $("#catalog-grid").innerHTML = items.map((item) => `<article class="catalog-card"><div class="catalog-card-top"><span class="catalog-platform">${item.platform}</span><span class="service-type-badge">${item.type}</span></div><h3>${item.name}</h3><p>${item.category || "Serviço do fornecedor"}</p><div class="catalog-values"><span>Custo / 1k<strong>R$ ${item.rate_fornecedor.toFixed(2)}</strong></span><span>Venda / 1k<strong>R$ ${item.preco_venda.toFixed(2)}</strong></span></div><div class="catalog-limits">${item.min.toLocaleString("pt-BR")} — ${item.max.toLocaleString("pt-BR")} unidades <button class="outline-button import-service" data-service="${item.service_id}">Importar para pedido →</button></div></article>`).join("") || `<div class="catalog-alert"><strong>Nenhum serviço corresponde aos filtros.</strong><span>Tente remover a busca ou selecionar outra plataforma.</span><button class="outline-button" id="clear-catalog-filters" type="button">Limpar filtros</button></div>`;
  const clearFilters = $("#clear-catalog-filters");
  if (clearFilters) clearFilters.addEventListener("click", () => { $("#catalog-search").value = ""; $("#catalog-platform").value = ""; renderCatalog(); });
  document.querySelectorAll(".import-service").forEach((button) => button.addEventListener("click", () => {
    $("#service").value = button.dataset.service;
    const item = state.services.find((service) => service.service_id === button.dataset.service);
    if (item) $("#platform").value = item.platform;
    $("#new-order").scrollIntoView({ behavior: "smooth" });
    updateServiceOptions();
    $("#service").value = button.dataset.service;
    updateEstimate();
  }));
}

function updateServiceFields() {
  const comments = isCommentsService();
  $("#comments-field").classList.toggle("visible", comments);
  $("#quantity-row").classList.toggle("hidden", comments);
  $("#quantity").disabled = comments;
  $("#quantity").required = !comments;
  $("#comentarios-input").required = comments;
  updateEstimate();
}

function statusLabel(status) {
  return { pending: ["Pendente", "status-pending"], paid: ["Pago", "status-paid"], processing: ["Processando", "status-processing"], completed: ["Concluído", "status-completed"] }[status] || [status, "status-pending"];
}

async function loadOrders() {
  const query = new URLSearchParams({ search: $("#search").value, status: $("#status-filter").value });
  const orders = await api(`/api/pedidos?${query}`);
  const rows = orders.map((order) => {
    const [label, klass] = statusLabel(order.status);
    const date = order.created_at ? new Date(order.created_at).toLocaleDateString("pt-BR") : "—";
    return `<tr><td><span class="order-link" title="${order.link}">#${String(order.id).padStart(5, "0")} · ${order.link}</span></td><td>${order.plataforma}</td><td>${order.tipo_servico}</td><td>${order.service_name}</td><td>${order.quantity.toLocaleString("pt-BR")}</td><td>${money(order.customer_price)}</td><td><span class="status ${klass}">${label}</span></td><td>${date}</td><td>···</td></tr>`;
  });
  $("#orders-table").innerHTML = rows.join("") || `<tr><td colspan="7" class="empty">Nenhum pedido encontrado.</td></tr>`;
}

async function loadKpis() {
  const data = await api("/api/dashboard/kpis");
  $("#revenue-kpi").textContent = money(data.revenue);
  $("#profit-kpi").textContent = money(data.profit);
  $("#orders-kpi").textContent = data.sales.toLocaleString("pt-BR");
  $("#completed-kpi").textContent = `${data.completed} concluídos`;
}

function openPayment(payment) {
  $("#qr-image").src = `data:image/png;base64,${payment.qr_code_base64}`;
  $("#pix-code").textContent = payment.qr_code || "Código PIX indisponível";
  $("#payment-modal").classList.add("open");
  let remaining = 1800;
  clearInterval(state.timer);
  state.timer = setInterval(() => { remaining -= 1; $("#timer").textContent = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`; if (remaining <= 0) clearInterval(state.timer); }, 1000);
}

function toast(message) { $("#toast").textContent = message; $("#toast").classList.add("show"); setTimeout(() => $("#toast").classList.remove("show"), 2800); }

$("#platform").addEventListener("change", updateEstimate);
$("#service-type").addEventListener("change", updateServiceFields);
$("#quantity").addEventListener("input", updateEstimate);
$("#comentarios-input").addEventListener("input", updateEstimate);
$("#search").addEventListener("input", loadOrders);
$("#status-filter").addEventListener("change", loadOrders);
$("#new-order-button").addEventListener("click", () => $("#new-order").scrollIntoView({ behavior: "smooth" }));
$("#close-modal").addEventListener("click", () => $("#payment-modal").classList.remove("open"));
$("#payment-modal").addEventListener("click", (event) => { if (event.target.id === "payment-modal") $("#payment-modal").classList.remove("open"); });
$("#copy-pix").addEventListener("click", async () => { await navigator.clipboard.writeText($("#pix-code").textContent); $("#copy-pix").textContent = "Copiado"; toast("Código PIX copiado."); setTimeout(() => $("#copy-pix").textContent = "Copiar", 1600); });
$("#export-button").addEventListener("click", async () => {
  askAdminKey();
  const response = await fetch("/api/pedidos/exportar", { headers: { "X-Admin-Key": adminKey } });
  if (!response.ok) { toast("Chave administrativa inválida ou ausente."); return; }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "relatorio-pedidos.csv"; link.click();
  URL.revokeObjectURL(url);
});
$("#order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true; button.textContent = "Gerando PIX...";
  try {
    const data = await api("/api/pedidos/criar", { method: "POST", body: JSON.stringify({ link: $("#link").value, plataforma: $("#platform").value, tipo_servico: $("#service-type").value, service_id: serviceId(), quantity: isCommentsService() ? null : Number($("#quantity").value), comentarios: isCommentsService() ? $("#comentarios-input").value : null, payer_email: $("#email").value }) });
    openPayment(data.payment); event.currentTarget.reset(); $("#quantity").value = 1000; updateServiceFields(); await Promise.all([loadOrders(), loadKpis()]);
  } catch (error) { toast(error.message); } finally { button.disabled = false; button.innerHTML = "Gerar cobrança PIX <span>→</span>"; }
});

updateServiceFields();
Promise.all([loadServices(), loadOrders(), loadKpis()]).catch((error) => toast(error.message));

async function loadAnalytics() {
  const data = await api("/api/analytics");
  $("#analytics-7").textContent = money(data.revenue_7_days);
  $("#analytics-30").textContent = money(data.revenue_30_days);
  $("#analytics-profit").textContent = money(data.net_profit);
  $("#analytics-conversion").textContent = `${data.conversion_rate}%`;
  if (state.revenueChart) state.revenueChart.destroy();
  if (state.platformChart) state.platformChart.destroy();
  state.revenueChart = new Chart($("#revenue-chart"), { type: "line", data: { labels: data.daily.map((item) => item.date.slice(5)), datasets: [{ label: "Faturamento", data: data.daily.map((item) => item.revenue), borderColor: "#7bf0c5", backgroundColor: "rgba(123,240,197,.12)", fill: true, tension: .35 }, { label: "Lucro", data: data.daily.map((item) => item.profit), borderColor: "#8ba9ff", backgroundColor: "transparent", tension: .35 }] }, options: { responsive: true, plugins: { legend: { labels: { color: "#b5c0ca" } } }, scales: { x: { ticks: { color: "#687685" }, grid: { color: "#263441" } }, y: { ticks: { color: "#687685" }, grid: { color: "#263441" } } } } });
  state.platformChart = new Chart($("#platform-chart"), { type: "doughnut", data: { labels: data.platforms.map((item) => item.platform), datasets: [{ data: data.platforms.map((item) => item.sales), backgroundColor: ["#7bf0c5", "#8ba9ff", "#ffb86b", "#c8b0ff"], borderColor: "#111820" }] }, options: { plugins: { legend: { labels: { color: "#b5c0ca" } } } } });
}

async function loadConfig() {
  const data = await api("/api/config");
  $("#smm-api-url").value = data.smm_api_url;
  $("#margin").value = data.margem_lucro_padrao_porcentagem;
}

$("#platform").addEventListener("change", updateServiceOptions);
$("#service-type").addEventListener("change", updateServiceOptions);
$("#catalog-search").addEventListener("input", renderCatalog);
$("#catalog-platform").addEventListener("change", renderCatalog);
$("#sync-catalog").addEventListener("click", async () => { $("#sync-catalog").disabled = true; $("#sync-catalog").textContent = "Sincronizando..."; await loadServices(); $("#sync-catalog").disabled = false; $("#sync-catalog").textContent = "↻ Sincronizar"; });
$("#refresh-analytics").addEventListener("click", loadAnalytics);
$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/config", { method: "POST", body: JSON.stringify({ smm_api_url: $("#smm-api-url").value, smm_api_key: $("#smm-api-key").value, mercadopago_access_token: $("#mp-token").value, margem_lucro_padrao_porcentagem: Number($("#margin").value) }) });
    toast("Configurações salvas.");
    await loadServices();
  } catch (error) { toast(error.message); }
});
$("#test-connections").addEventListener("click", async () => {
  $("#connection-status").textContent = "Testando fornecedor...";
  try {
    const [balance] = await Promise.all([api("/api/smm/saldo"), api("/api/mercadopago/testar")]);
    $("#connection-status").textContent = `SMM e Mercado Pago conectados · saldo ${balance.balance} ${balance.currency || ""}`;
    toast("Conexões SMM e Mercado Pago validadas.");
  } catch (error) { $("#connection-status").textContent = error.message; toast(error.message); }
});
loadConfig().catch(() => {});
loadAnalytics().catch(() => {});
