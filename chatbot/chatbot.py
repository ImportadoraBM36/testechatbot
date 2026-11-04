import re

from .produtos import buscar_produtos, pesquisar_produtos

SAUDACOES = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"}

# Catálogos disponíveis (valor do botão -> nome exibido).
# Os valores precisam estar em minúsculas, porque a mensagem é normalizada com .lower().
CATALOGOS = {
    "vidro": "Vidro",
    "embalagem": "Embalagem",
    "frascos": "Frascos",
    "papelaria/talheres/presentes": "Papelaria/Talheres/Presentes",
}

# Filtros de cada catálogo: (texto do botão, valor, palavras que procuramos no nome)
# Catálogos sem filtros aqui mostram todos os produtos direto.
FILTROS = {
    "vidro": [
        ("Vidros", "vidro", ("vidro",)),
        ("Porta-Jóias", "joias", ("porta-jóias",)),
        ("Porcelanas", "porcelana", ("coleção",)),
        ("Melamina", "melamina", ("melamina",)),
    ],
    "papelaria/talheres/presentes": [
        ("Cromado / Inox", "cromado", ("cromado",)),
        ("Dourado", "dourado", ("dourado",)),
        ("Bicolor", "bicolor", ("bicolor",)),
        ("Preto e Verde", "cores", ("preto", "verde")),
    ],
}

# valor do botão (minúsculo) -> texto salvo no cadastro
TIPOS_LOJA = {
    "industria": "Indústria",
    "distribuidora": "Distribuidora",
    "atacado": "Atacado",
    "varejo": "Consumidor final/varejo",
}

COMANDOS_INICIO = {
    "inicio",
    "início",
    "voltar",
    "voltar_inicio",
    "voltar ao inicio",
    "voltar ao início",
    "voltar do inicio",
    "voltar do início",
    "menu inicial",
    "reiniciar",
}


def _opcoes(*itens):
    return [{"texto": texto, "valor": valor} for texto, valor in itens]


def _menu_cadastro(texto):
    return {
        "tipo": "menu",
        "texto": texto,
        "opcoes": _opcoes(
            ("Sim, já sou cliente", "sim"),
            ("Ainda não sou cliente", "nao"),
            ("Quero ver produtos", "produtos"),
        ),
    }


def _catalogos(texto="Qual catálogo você deseja ver?"):
    return {
        "tipo": "menu",
        "texto": texto,
        "opcoes": _opcoes(
            ("Vidro", "vidro"),
            ("Embalagem", "embalagem"),
            ("Frascos", "frascos"),
            ("Papelaria/Talheres/Presentes", "papelaria/talheres/presentes"),
            ("Pesquisar produto", "pesquisar"),
            ("Falar com atendente", "atendente"),
        ),
    }


def _menu_tipo_loja(texto):
    return {
        "tipo": "menu",
        "texto": texto,
        "opcoes": _opcoes(
            ("Indústria", "industria"),
            ("Distribuidora", "distribuidora"),
            ("Atacado", "atacado"),
            ("Consumidor final/varejo", "varejo"),
            ("Outro", "outro"),
        ),
    }


def _menu_filtros(catalogo):
    opcoes = [(texto, f"f:{valor}") for texto, valor, _ in FILTROS[catalogo]]
    opcoes.append(("Ver tudo", "f:todos"))
    return {
        "tipo": "menu",
        "texto": "Selecione alguma opção",
        "opcoes": _opcoes(*opcoes),
    }


def _filtrar(catalogo, filtro):
    if filtro == "todos":
        return buscar_produtos(catalogo)

    for _, valor, palavras in FILTROS.get(catalogo, []):
        if valor == filtro:
            return buscar_produtos(catalogo, palavras)

    return buscar_produtos(catalogo)


def _resposta_produtos(catalogo, produtos):
    """Monta a resposta com a lista de produtos de um catálogo."""
    opcoes = []
    if catalogo in FILTROS:
        opcoes.append(("Outro filtro", f"filtros:{catalogo}"))
    opcoes += [
        ("Pesquisar produto", "pesquisar"),
        ("Ver outro catálogo", "produtos"),
        ("Falar com atendente", "atendente"),
    ]
    return {
        "tipo": "produtos",
        "texto": f"Encontrei {len(produtos)} produtos.",
        "produtos": produtos,
        "opcoes": _opcoes(*opcoes),
    }


def _resposta_atendente(texto="Seu atendimento foi encaminhado para a equipe comercial."):
    return {"tipo": "atendente", "texto": texto, "acao": "registrar_atendimento"}


def _cnpj_valido(cnpj):
    """Valida os dígitos verificadores (rejeita 11111111111111 etc.)."""
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def digito(base):
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):]
        resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = digito(cnpj[:12])
    d2 = digito(cnpj[:12] + d1)
    return cnpj[12:] == d1 + d2


def _documento_valido(texto):
    documento = re.sub(r"\D", "", texto)
    return documento if _cnpj_valido(documento) else None


def _formatar_cnpj(c):
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


# Letras (com acento), números, espaço e pontuação comum. Bloqueia < > { } etc.
_TEXTO_SEGURO = re.compile(r"^[\w\s.,&'’\-/()ªº]+$")


def _texto_valido(texto, minimo, maximo):
    """Devolve o texto limpo ou None se for inválido."""
    limpo = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", texto).split())
    if not (minimo <= len(limpo) <= maximo) or not _TEXTO_SEGURO.match(limpo):
        return None
    return limpo


def _menu_confirmar(estado):
    return {
        "tipo": "menu",
        "texto": (
            f"Confira seus dados — CNPJ: {_formatar_cnpj(estado['documento'])} | "
            f"Nome: {estado['nome']} | Tipo: {estado['tipo_loja']}. "
            "Ao confirmar, você autoriza a BM36 a usar esses dados para contato "
            "comercial. Seu cadastro passará por uma análise da nossa equipe."
        ),
        "opcoes": _opcoes(
            ("Confirmar cadastro", "confirmar"),
            ("Corrigir dados", "corrigir"),
        ),
    }


def _produto_por_codigo(catalogo, codigo):
    """Procura o produto no catálogo atual; se não achar (ex.: veio de uma
    pesquisa), procura em todos os produtos pelo código."""
    codigo = codigo.strip().upper()

    if catalogo:
        produto = next(
            (p for p in buscar_produtos(catalogo) if p["codigo"].upper() == codigo),
            None,
        )
        if produto:
            return produto

    return next(
        (p for p in pesquisar_produtos(codigo) if p["codigo"].upper() == codigo),
        None,
    )


def responder(mensagem, estado, cliente_existente=None, cadastro_pendente=False):
    """Decide todo o fluxo e atualiza o estado da sessão."""
    texto = str(mensagem or "").strip()
    normalizado = texto.lower()
    etapa = estado.get("etapa", "inicio")

    # Comando global: voltar ao menu inicial em qualquer etapa.
    # Aceita tanto texto digitado quanto valores de botões.
    if normalizado in COMANDOS_INICIO:
        estado.clear()
        estado["etapa"] = "cadastro"
        return _menu_cadastro(
            "Conversa reiniciada! 👋 Bem-vindo ao atendimento BM36. Você já é cadastrado?"
        )

    # 1) Começo da conversa
    if etapa == "inicio":
        # Ignora pontuação: "Oi!" também vale.
        saudacao = re.sub(r"[^\w\s]", "", normalizado).strip()
        if saudacao not in SAUDACOES:
            return {
                "tipo": "texto",
                "texto": "Para iniciar o atendimento, escreva 'oi'.",
            }

        estado["etapa"] = "cadastro"
        return _menu_cadastro(
            "Olá! 👋 Bem-vindo ao atendimento BM36. Você já é cadastrado?"
        )

    # 2) Cadastro existente ou novo
    if etapa == "cadastro":
        if normalizado == "sim":
            estado["etapa"] = "documento_cliente"
            return {
                "tipo": "texto",
                "texto": "Informe seu CNPJ para localizar o cadastro.",
            }

        if normalizado in {"nao", "não"}:
            estado["etapa"] = "documento_novo"
            return {
                "tipo": "texto",
                "texto": "Vamos fazer seu cadastro. Informe seu CNPJ.",
            }

        if normalizado == "produtos":
            estado["etapa"] = "catalogos"
            return _catalogos()

        return {"tipo": "texto", "texto": "Escolha uma das opções disponíveis."}

    # 3) CNPJ
    if etapa in {"documento_cliente", "documento_novo"}:
        documento = _documento_valido(texto)

        if not documento:
            return {
                "tipo": "texto",
                "texto": "CNPJ inválido. Confira os 14 dígitos e digite novamente.",
            }

        if cliente_existente:
            if etapa == "documento_novo":
                # Não expõe dados: apenas orienta a entrar como cliente.
                estado["etapa"] = "cadastro"
                return {
                    "tipo": "menu",
                    "texto": "Esse CNPJ já possui cadastro. Deseja entrar como cliente?",
                    "opcoes": _opcoes(
                        ("Sim, já sou cliente", "sim"),
                        ("Quero ver produtos", "produtos"),
                    ),
                }

            estado.update(documento=documento, nome=cliente_existente, etapa="catalogos")
            if cadastro_pendente:
                return _catalogos(
                    f"Encontramos seu cadastro, {cliente_existente}. "
                    "Ele está em análise, mas você já pode ver os catálogos."
                )
            return _catalogos(
                f"Cadastro localizado! Seja bem-vindo, {cliente_existente}. "
                "Selecione uma opção."
            )

        estado["documento"] = documento
        estado["etapa"] = "nome"

        if etapa == "documento_cliente":
            return {
                "tipo": "texto",
                "texto": (
                    "Não achei esse CNPJ. Vamos fazer seu cadastro. "
                    "Informe o nome ou a razão social da empresa."
                ),
            }

        return {
            "tipo": "texto",
            "texto": "Informe seu nome ou a razão social da empresa.",
        }

    # 4) Nome
    if etapa == "nome":
        nome = _texto_valido(texto, 2, 120)

        if not nome:
            return {
                "tipo": "texto",
                "texto": "Informe um nome ou razão social válido (sem símbolos como < > { }).",
            }

        estado.update(nome=nome, etapa="tipo_loja")
        return _menu_tipo_loja("Qual é o tipo da sua loja?")

    # 5) Tipo de loja
    if etapa == "tipo_loja":
        if normalizado in TIPOS_LOJA:
            estado.update(tipo_loja=TIPOS_LOJA[normalizado], etapa="confirmar")
            return _menu_confirmar(estado)

        if normalizado == "outro":
            estado["etapa"] = "tipo_outro"
            return {
                "tipo": "texto",
                "texto": "Qual é o tipo da sua loja? Escreva em poucas palavras.",
            }

        return _menu_tipo_loja("Escolha uma das opções abaixo.")

    if etapa == "tipo_outro":
        tipo = _texto_valido(texto, 2, 40)

        if not tipo:
            return {
                "tipo": "texto",
                "texto": "Escreva o tipo da sua loja (2 a 40 caracteres, sem símbolos).",
            }

        estado.update(tipo_loja=tipo.title(), etapa="confirmar")
        return _menu_confirmar(estado)

    # 5.1) Confirmação final: só aqui o cadastro é salvo
    if etapa == "confirmar":
        if normalizado == "confirmar":
            estado["etapa"] = "catalogos"
            resposta = _catalogos(
                f"Cadastro recebido, {estado['nome']}! Nossa equipe vai analisá-lo. "
                "Enquanto isso, escolha um catálogo:"
            )
            resposta["acao"] = "salvar_cliente"
            return resposta

        if normalizado == "corrigir":
            for chave in ("documento", "nome", "tipo_loja"):
                estado.pop(chave, None)
            estado["etapa"] = "documento_novo"
            return {
                "tipo": "texto",
                "texto": "Sem problemas. Informe novamente o seu CNPJ.",
            }

        return _menu_confirmar(estado)

    # 6) Escolher catálogo ou pesquisar
    if etapa in {"catalogos", "catalogo", "filtro"}:

        if normalizado == "pesquisar":
            estado["etapa"] = "pesquisar_produto"
            return {
                "tipo": "texto",
                "texto": "🔎 Digite o nome ou o código do produto que deseja encontrar.",
            }

        if normalizado in CATALOGOS:
            estado["catalogo"] = normalizado

            # Catálogo com filtros: mostra o menu de filtros
            if normalizado in FILTROS:
                estado["etapa"] = "filtro"
                return _menu_filtros(normalizado)

            # Catálogo sem filtros: mostra todos os produtos direto
            produtos = buscar_produtos(normalizado)
            if not produtos:
                return {
                    "tipo": "texto",
                    "texto": "Ainda não há produtos nesse catálogo.",
                }
            estado["etapa"] = "catalogo"
            return _resposta_produtos(normalizado, produtos)

        # 7) Aplicar filtro do catálogo
        if normalizado.startswith("f:") and estado.get("catalogo"):
            catalogo = estado["catalogo"]
            produtos = _filtrar(catalogo, normalizado[2:])

            if not produtos:
                return {
                    "tipo": "texto",
                    "texto": "Não encontrei produtos nesse filtro.",
                }

            estado["etapa"] = "catalogo"
            return _resposta_produtos(catalogo, produtos)

        if normalizado.startswith("filtros:"):
            catalogo = normalizado.split(":", 1)[1]

            if catalogo in FILTROS:
                estado.update(catalogo=catalogo, etapa="filtro")
                return _menu_filtros(catalogo)

        if normalizado == "produtos":
            estado["etapa"] = "catalogos"
            return _catalogos()

        if normalizado == "atendente":
            estado["etapa"] = "atendente"
            return _resposta_atendente()

        if normalizado.startswith("produto:"):
            produto = _produto_por_codigo(
                estado.get("catalogo", ""),
                normalizado.split(":", 1)[1],
            )

            if not produto:
                return {
                    "tipo": "texto",
                    "texto": "Não encontrei esse produto no catálogo atual.",
                }

            estado.update(produto=produto, etapa="atendente")
            return _resposta_atendente(
                f"Ótima escolha: {produto['nome']}. Vou encaminhar você a um atendente."
            )

        return {"tipo": "texto", "texto": "Use os botões disponíveis para continuar."}

    # 8) Pesquisar produto pelo nome ou código
    if etapa == "pesquisar_produto":
        if normalizado == "produtos":
            estado["etapa"] = "catalogos"
            return _catalogos()

        if normalizado == "atendente":
            estado["etapa"] = "atendente"
            return _resposta_atendente()

        produtos = pesquisar_produtos(texto)

        if not produtos:
            return {
                "tipo": "texto",
                "texto": (
                    "Não encontrei produtos com esse nome ou código. "
                    "Tente pesquisar de outra forma ou digite 'produtos' "
                    "para voltar ao catálogo."
                ),
            }

        estado["etapa"] = "catalogo"

        return {
            "tipo": "produtos",
            "texto": f"Encontrei {len(produtos)} produto(s) para sua pesquisa.",
            "produtos": produtos,
            "opcoes": _opcoes(
                ("Pesquisar outro produto", "pesquisar"),
                ("Ver catálogos", "produtos"),
                ("Falar com atendente", "atendente"),
            ),
        }

    # 9) Atendimento
    if etapa == "atendente":
        if normalizado == "produtos":
            estado["etapa"] = "catalogos"
            return _catalogos()

        return {
            "tipo": "texto",
            "texto": (
                "Seu pedido já foi encaminhado. "
                "Digite 'produtos' para voltar aos catálogos."
            ),
        }

    # 10) Recuperação de fluxo desconhecido
    # Volta diretamente ao menu inicial, sem exigir "oi" novamente.
    estado.clear()
    estado["etapa"] = "cadastro"
    return _menu_cadastro("Vamos recomeçar! 👋 Você já é cadastrado?")