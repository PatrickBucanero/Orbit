const menuButton = document.querySelector("#menu-button");
const navLinks = document.querySelector(".nav-links");
menuButton?.addEventListener("click", () => navLinks.classList.toggle("open"));
document.querySelectorAll('a[href^="#"]').forEach((link) => link.addEventListener("click", () => navLinks.classList.remove("open")));

const orderState = { services: [] };
const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value || 0);
const publicApi = async (path, options = {}) => {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok || payload.sucesso === false) throw new Error(payload.erro || payload.detail || "Não foi possível concluir.");
  return payload;
};

function publicTypeMatches(item, type) {
  const text = `${item.name} ${item.category}`.toLowerCase();
  if (type === "comentarios") return item.type === "custom_comments" || text.includes("comment") || text.includes("coment");
  if (type === "curtidas") return text.includes("like") || text.includes("curtida");
  if (type === "visualizacoes") return text.includes("view") || text.includes("visualiza");
  return text.includes("follower") || text.includes("subscriber") || text.includes("segu") || text.includes("inscri");
}

function updatePublicServices() {
  const platform = document.querySelector("#public-platform").value.toLowerCase();
  const type = document.querySelector("#public-type").value;
  const matches = orderState.services.filter((item) => item.platform.toLowerCase().includes(platform) && publicTypeMatches(item, type));
  const fallback = orderState.services.filter((item) => item.platform.toLowerCase().includes(platform));
  const select = document.querySelector("#public-service");
  select.replaceChildren();
  const services = matches.length ? matches : fallback;
  if (!services.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Serviço indisponível";
    select.append(option);
  } else {
    services.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.service_id;
      option.textContent = `${item.name} · ${money(item.preco_venda)}/1k`;
      select.append(option);
    });
  }
  updatePublicTotal();
}

function updatePublicTotal() {
  const selected = orderState.services.find((item) => item.service_id === document.querySelector("#public-service").value);
  const comments = document.querySelector("#public-type").value === "comentarios";
  const quantity = comments ? document.querySelector("#public-comments").value.split("\n").filter((line) => line.trim()).length : Number(document.querySelector("#public-quantity").value) || 0;
  document.querySelector("#public-total").textContent = money(selected ? selected.preco_venda * quantity / 1000 : 0);
}

async function loadPublicServices() {
  const response = await publicApi("/api/catalogo");
  orderState.services = response.servicos || [];
  updatePublicServices();
}

function openPublicPayment(payment) {
  document.querySelector("#public-qr").src = `data:image/png;base64,${payment.qr_code_base64}`;
  document.querySelector("#public-pix-code").textContent = payment.qr_code || "Código PIX indisponível";
  document.querySelector("#public-payment-modal").classList.add("open");
}

document.querySelectorAll(".card-buy").forEach((button) => button.addEventListener("click", () => {
  document.querySelector("#public-type").value = button.dataset.type;
  updatePublicServices();
  document.querySelector("#comprar").scrollIntoView({ behavior: "smooth" });
}));
document.querySelector("#public-platform").addEventListener("change", updatePublicServices);
document.querySelector("#public-type").addEventListener("change", () => {
  const comments = document.querySelector("#public-type").value === "comentarios";
  document.querySelector("#public-comments-label").classList.toggle("visible", comments);
  document.querySelector("#public-quantity-label").style.display = comments ? "none" : "block";
  document.querySelector("#public-quantity").required = !comments;
  document.querySelector("#public-comments").required = comments;
  updatePublicServices();
});
document.querySelector("#public-service").addEventListener("change", updatePublicTotal);
document.querySelector("#public-quantity").addEventListener("input", updatePublicTotal);
document.querySelector("#public-comments").addEventListener("input", updatePublicTotal);
document.querySelector("#payment-close").addEventListener("click", () => document.querySelector("#public-payment-modal").classList.remove("open"));
document.querySelector("#public-payment-modal").addEventListener("click", (event) => { if (event.target.id === "public-payment-modal") event.currentTarget.classList.remove("open"); });
document.querySelector("#public-copy-pix").addEventListener("click", async () => { await navigator.clipboard.writeText(document.querySelector("#public-pix-code").textContent); document.querySelector("#public-copy-pix").textContent = "Copiado"; });
document.querySelector("#public-order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const feedback = document.querySelector("#public-feedback");
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true; feedback.textContent = "Gerando sua cobrança PIX...";
  const comments = document.querySelector("#public-type").value === "comentarios";
  try {
    const response = await publicApi("/api/pedidos/criar", { method: "POST", body: JSON.stringify({ plataforma: document.querySelector("#public-platform").value, tipo_servico: document.querySelector("#public-type").value, service_id: document.querySelector("#public-service").value, link: document.querySelector("#public-link").value, quantity: comments ? null : Number(document.querySelector("#public-quantity").value), comentarios: comments ? document.querySelector("#public-comments").value : null, payer_email: document.querySelector("#public-email").value }) });
    openPublicPayment(response.payment); feedback.textContent = "";
  } catch (error) { feedback.textContent = error.message; } finally { button.disabled = false; }
});

loadPublicServices().catch((error) => {
  const select = document.querySelector("#public-service");
  select.replaceChildren();
  const option = document.createElement("option");
  option.value = "";
  option.textContent = "Configure o catálogo para comprar";
  select.append(option);
  document.querySelector("#public-feedback").textContent = error.message;
});

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add("visible"); });
}, { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((element) => observer.observe(element));
