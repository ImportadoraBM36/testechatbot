import os
import re
import sqlite3
import time
import psycopg
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from chatbot import responder, _menu_confirmar

BASE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")


@app.get("/teste-banco")
def teste_banco():
    if not DATABASE_URL:
        return {
            "ok": False,
            "erro": "DATABASE_URL não foi encontrada no .env"
        }

    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as conexao:
            conexao.execute("SELECT 1")

        return {
            "ok": True,
            "mensagem": "Conexão com PostgreSQL funcionando!"
        }
    except Exception:
        return {
            "ok": False,
            "erro": "Falha na conexão. Confira a URL e as configurações."
        }
BANCO_CLIENTES = os.path.join(BASE, "clientes.db")
SESSOES = {}

# Limite simples contra cadastros em massa: 5 por IP a cada hora.
LIMITE_CADASTROS = 5
JANELA_SEGUNDOS = 3600
_cadastros_por_ip = {}


def _recentes(ip):
    agora = time.time()
    lista = [t for t in _cadastros_por_ip.get(ip, []) if agora - t < JANELA_SEGUNDOS]
    _cadastros_por_ip[ip] = lista
    return lista


# Compara só os dígitos, então funciona se o outro sistema guarda o CNPJ com ou sem pontuação.
SQL_DOCUMENTO = "regexp_replace(documento, '\\D', '', 'g') = %s"


def buscar_cliente(documento: str):
    """Retorna (nome, pendente). 'Pendente' = cadastro existe, mas ainda não está ativo."""
    if not DATABASE_URL:
        return None, False

    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as conexao:
            linha = conexao.execute(
                f"SELECT nome, ativo FROM clientes WHERE {SQL_DOCUMENTO} "
                "ORDER BY ativo DESC LIMIT 1",
                (documento,),
            ).fetchone()
    except Exception as erro:
        print("Erro ao consultar clientes no PostgreSQL:", erro)
        return None, False

    if not linha:
        return None, False
    return linha[0], not linha[1]


def salvar_cliente(documento: str, nome: str, tipo_loja: str) -> bool:
    """
    Grava o autocadastro em 'clientes' como INATIVO (ativo = FALSE) até alguém aprovar.
    Não duplica: se o CNPJ já existir, não insere nada. Retorna False se falhar.
    """
    if not DATABASE_URL:
        return False

    observacao = f"Autocadastro pelo chatbot - aguardando aprovação. Tipo de loja: {tipo_loja}"

    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as conexao:
            conexao.execute(
                f"""
                INSERT INTO clientes
                    (nome, documento, ativo, observacoes, criado_em, atualizado_em)
                SELECT %s, %s, FALSE, %s, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM clientes WHERE {SQL_DOCUMENTO}
                )
                """,
                (nome, documento, observacao, documento),
            )
        return True
    except Exception as erro:
        print("Erro ao salvar cliente no PostgreSQL:", erro)
        return False


def normalizar_documento(documento: str) -> str:
    return re.sub(r"\D", "", documento or "")


def preparar_banco() -> None:
    with sqlite3.connect(BANCO_CLIENTES) as conexao:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS atendimentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documento TEXT,
                nome TEXT,
                produto_codigo TEXT,
                produto_nome TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


preparar_banco()

# As imagens ficam na pasta "img" -> acessíveis em /img/nome.jpg
app.mount("/img", StaticFiles(directory=os.path.join(BASE, "img")), name="img")


@app.get("/", response_class=HTMLResponse)
def inicio():
    with open(os.path.join(BASE, "index.html"), "r", encoding="utf-8") as arquivo:
        return arquivo.read()


@app.get("/style.css")
def estilo():
    return FileResponse(os.path.join(BASE, "style.css"), media_type="text/css")


@app.get("/script.js")
def javascript():
    return FileResponse(os.path.join(BASE, "script.js"), media_type="application/javascript")


@app.post("/mensagem")
async def mensagem(request: Request):
    dados = await request.json()
    texto = dados.get("mensagem", "")
    identificador = str(dados.get("sessao") or "anonimo")
    estado = SESSOES.setdefault(identificador, {"etapa": "inicio"})

    ip = request.client.host if request.client else "desconhecido"

    # Trava de segurança antes de salvar um novo cadastro
    if (
        estado.get("etapa") == "confirmar"
        and str(texto).strip().lower() == "confirmar"
        and len(_recentes(ip)) >= LIMITE_CADASTROS
    ):
        return {
            "tipo": "texto",
            "texto": "Muitas tentativas de cadastro. Tente novamente mais tarde.",
        }

    cliente_existente, pendente = None, False
    if estado.get("etapa") in {"documento_cliente", "documento_novo"}:
        documento = normalizar_documento(texto)
        if len(documento) == 14:
            cliente_existente, pendente = buscar_cliente(documento)

    resposta = responder(texto, estado, cliente_existente, pendente)

    if resposta.get("acao") == "salvar_cliente":
        if salvar_cliente(estado["documento"], estado["nome"], estado.get("tipo_loja", "")):
            _recentes(ip).append(time.time())
        else:
            # Não diga "cadastro recebido" se não gravou: volta para a confirmação.
            estado["etapa"] = "confirmar"
            resposta = _menu_confirmar(estado)
            resposta["texto"] = (
                "Não consegui concluir o cadastro agora. Tente confirmar novamente. "
                + resposta["texto"]
            )

    if resposta.get("acao") == "registrar_atendimento":
        produto = estado.get("produto", {})
        with sqlite3.connect(BANCO_CLIENTES) as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO atendimentos (documento, nome, produto_codigo, produto_nome)
                VALUES (?, ?, ?, ?)
                """,
                (
                    estado.get("documento", ""), estado.get("nome", ""),
                    produto.get("codigo", ""), produto.get("nome", ""),
                ),
            )
        resposta["texto"] += f" Protocolo #{cursor.lastrowid}."

    return resposta


@app.post("/atendimentos")
async def encaminhar_atendimento(request: Request):
    """Registra o interesse na fila comercial da demonstração."""
    dados = await request.json()
    produto = dados.get("produto") or {}
    documento = normalizar_documento(dados.get("documento", ""))
    nome = " ".join(str(dados.get("nome", "")).split())

    with sqlite3.connect(BANCO_CLIENTES) as conexao:
        cursor = conexao.execute(
            """
            INSERT INTO atendimentos (documento, nome, produto_codigo, produto_nome)
            VALUES (?, ?, ?, ?)
            """,
            (documento, nome, produto.get("codigo", ""), produto.get("nome", "")),
        )

    return {"ok": True, "protocolo": cursor.lastrowid}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)