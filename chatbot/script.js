const conversa = document.querySelector("#conversa");
const input = document.querySelector("#mensagem");
const form = document.querySelector("#form");
const status = document.querySelector("#status");
const chave = "bm36-sessao";
const sessao = localStorage.getItem(chave) || crypto.randomUUID();
localStorage.setItem(chave, sessao);

function esc(texto) { return String(texto ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function rolar() { conversa.scrollTop = conversa.scrollHeight; }
function mensagem(texto, quem = "bot") { conversa.insertAdjacentHTML("beforeend", `<div class="bubble ${quem}">${esc(texto)}<span class="time">${new Date().toLocaleTimeString("pt-BR", {hour:"2-digit",minute:"2-digit"})}</span></div>`); rolar(); }
function carregando() { const e = document.createElement("div"); e.className = "typing"; e.innerHTML = "<i></i><i></i><i></i>"; conversa.append(e); rolar(); return e; }

async function consultar(mensagem) {
  const r = await fetch("/mensagem", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mensagem, sessao }) });
  if (!r.ok) throw Error("Servidor indisponível");
  return r.json();
}

function mostrarOpcoes(lista = []) {
  if (!lista.length) return;
  const grupo = document.createElement("div"); grupo.className = "choices";
  lista.forEach(opcao => { const b = document.createElement("button"); b.type = "button"; b.textContent = opcao.texto; b.onclick = () => enviar(opcao.valor, opcao.texto, grupo); grupo.append(b); });
  conversa.append(grupo); rolar();
}

function mostrarProdutos(lista = []) {
  const carrossel = document.createElement("div"); carrossel.className = "carousel";
  lista.forEach(p => {
    const card = document.createElement("article"); card.className = "card";
    let imagem;
    if (p.imagem) {
      imagem = document.createElement("img");
      imagem.src = `/${p.imagem.replace(/^\//, "")}`;
      imagem.alt = p.nome;
      imagem.onerror = () => {
        imagem.replaceWith(criarImagemIndisponivel());
      };
    } else {
      imagem = criarImagemIndisponivel();
    }
    const titulo = document.createElement("h3"); titulo.textContent = p.nome;
    const codigo = document.createElement("p"); codigo.textContent = `Cód. ${p.codigo}`;
    const b = document.createElement("button"); b.type = "button"; b.textContent = "Tenho interesse"; b.onclick = () => enviar(`produto:${p.codigo}`, `Tenho interesse no ${p.nome}`);
    card.append(imagem, titulo, codigo, b); carrossel.append(card);
  });
  conversa.append(carrossel); rolar();
}

function criarImagemIndisponivel() {
  const aviso = document.createElement("div");
  aviso.className = "no-image";
  aviso.textContent = "Imagem indisponível";
  return aviso;
}

function mostrar(resposta) {
  if (resposta.texto) mensagem(resposta.texto);
  if (resposta.produtos) mostrarProdutos(resposta.produtos);

  // Toda etapa oferece uma saída segura para conversas que saíram do fluxo.
  const opcoes = [...(resposta.opcoes || [])];
  if (!opcoes.some(opcao => opcao.valor === "reiniciar")) {
    opcoes.push({ texto: "Voltar ao início", valor: "reiniciar" });
  }
  mostrarOpcoes(opcoes);

  if (resposta.tipo === "atendente") status.textContent = "Encaminhado ao atendimento";
}

async function enviar(valor, exibicao = valor, grupo = null) {
  if (grupo) grupo.querySelectorAll("button").forEach(b => b.disabled = true);
  mensagem(exibicao, "user");
  const espera = carregando();
  try { mostrar(await consultar(valor)); } catch (erro) { console.error(erro); mensagem("Não consegui falar com o servidor. Tente novamente."); } finally { espera.remove(); }
}

form.onsubmit = evento => { evento.preventDefault(); const texto = input.value.trim(); if (!texto) return; input.value = ""; enviar(texto); };
