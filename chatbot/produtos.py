
import os
import re
import unicodedata

import psycopg
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
PASTA_IMG = os.path.join(BASE, "img")
DATABASE_URL = os.getenv("DATABASE_URL")


def _chave_imagem(valor):
    """Normaliza o código usado no nome do arquivo de imagem."""
    texto = str(valor or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))

    # Sufixos usado em alguns arquivos enviados para a pasta de imagens.
    texto = re.sub(
        r"(?:[_\s-]+(?:OK(?:AY)?|ATUALIZADA|NAO\s*TEM))+$",
        "",
        texto,
    )

    # Trata BM-360593, BM360593 e BM 360593 como o mesmo código.
    return re.sub(r"[^A-Z0-9]", "", texto)


def _indexar_imagens():
    indice = {}

    if not os.path.isdir(PASTA_IMG):
        print("ATENÇÃO: pasta de imagens não encontrada:", PASTA_IMG)
        return indice

    arquivos = []

    for arquivo in os.listdir(PASTA_IMG):
        nome, ext = os.path.splitext(arquivo)

        caminho = os.path.join(PASTA_IMG, arquivo)
        if (
            ext.lower() not in (".jpg", ".jpeg", ".png", ".webp")
            or os.path.getsize(caminho) == 0
        ):
            continue

        chave = _chave_imagem(nome)
        if not chave:
            continue

        # Prioriza imagens revisadas, quando houver mais de uma para o código.
        prioridade = (
            0 if re.search(r"(?:_|\s)OK(?:AY)?$", nome, re.IGNORECASE) else 1
        )

        arquivos.append((prioridade, chave, arquivo))

    # As imagens _OK são processadas primeiro.
    arquivos.sort(key=lambda item: item[0])

    for prioridade, chave, arquivo in arquivos:
        indice.setdefault(chave, arquivo)

    return indice


IMAGENS = _indexar_imagens()

IMAGEM_PADRAO = (
    "17.jpg"
    if os.path.isfile(os.path.join(PASTA_IMG, "17.jpg"))
    else ""
)


def achar_imagem(*codigos):
    """Procura primeiro pelo código do fabricante e depois pelo código de barras."""
    for codigo in codigos:
        nome_arquivo = IMAGENS.get(_chave_imagem(codigo))
        if nome_arquivo:
            return f"img/{nome_arquivo}"

    return None



def _formatar_produtos(linhas):
    resultado = []

    for codigo_barras, codigo_fabricante, nome, preco, quantidade in linhas:
        codigo_interno = str(codigo_fabricante or "").strip().upper()

        if not codigo_interno:
            codigo_interno = str(codigo_barras or "").strip()

        resultado.append({
            "codigo": codigo_interno,
            "codigo_barras": str(codigo_barras or ""),
            "nome": nome or "",
            "preco": float(preco) if preco is not None else None,
            "quantidade_por_caixa": (
                float(quantidade) if quantidade is not None else None
            ),
            "imagem": achar_imagem(codigo_interno, codigo_barras),
        })

    return resultado



def buscar_produtos(catalogo, termos=()):
    if not DATABASE_URL:
        print("ERRO: DATABASE_URL não encontrada no .env")
        return []

    filtros = {
        "cozinha": (
            "%castiçal%",
            "%porta-jóias%",
            "%coleção%",
            "%melamina%",
        ),
        "talheres": (
            "%cromado%",
            "%inox%",
            "%dourado%",
            "%bicolor%",
            "%preto%",
            "%verde%",
        ),
    }

    if catalogo not in filtros:
        return []

    condicoes_catalogo = " OR ".join(
        ["nome ILIKE %s"] * len(filtros[catalogo])
    )
    condicoes_filtro = ""
    parametros = list(filtros[catalogo])

    if termos:
        condicoes_filtro = "\n          AND (" + " OR ".join(
            ["nome ILIKE %s"] * len(termos)
        ) + ")"
        parametros.extend(f"%{termo}%" for termo in termos)

    sql = f"""
        SELECT codigo, codigo_fabricante, nome, preco_venda, quantidade_por_caixa
        FROM produtos
        WHERE ativo = TRUE
          AND ({condicoes_catalogo}){condicoes_filtro}
        ORDER BY nome
        LIMIT 200
    """

    try:
        with psycopg.connect(
            DATABASE_URL,
            connect_timeout=5,
        ) as conexao:
            linhas = conexao.execute(
                sql,
                parametros,
            ).fetchall()

        return _formatar_produtos(linhas)

    except Exception as erro:
        print("Erro ao consultar produtos no PostgreSQL:", erro)
        return []


def pesquisar_produtos(termo):
    if not DATABASE_URL:
        print("ERRO: DATABASE_URL não encontrada no .env")
        return []

    termo = str(termo or "").strip()

    if len(termo) < 2:
        return []

    busca = f"%{termo}%"

    sql = """
        SELECT codigo, codigo_fabricante, nome, preco_venda, quantidade_por_caixa
        FROM produtos
        WHERE ativo = TRUE
          AND (
              codigo::text ILIKE %s
              OR nome ILIKE %s
          )
        ORDER BY nome
        LIMIT 10
    """

    try:
        with psycopg.connect(
            DATABASE_URL,
            connect_timeout=5,
        ) as conexao:
            linhas = conexao.execute(
                sql,
                (busca, busca),
            ).fetchall()

        return _formatar_produtos(linhas)

    except Exception as erro:
        print("Erro ao pesquisar produtos:", erro)
        return []
