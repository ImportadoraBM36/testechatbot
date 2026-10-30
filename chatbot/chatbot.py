import re

from .produtos import buscar_produtos, pesquisar_produtos

SAUDACOES = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"}

# Filtros de cada catálogo: (texto do botão, valor, palavras que procuramos no nome)
FILTROS = {
    "cozinha": [
        ("Castiçais", "castical", ("castiçal",)),
        ("Porta-Jóias", "joias", ("porta-jóias",)),
        ("Porcelanas", "porcelana", ("coleção",)),
        ("Melamina", "melamina", ("melamina",)),
    ],
    "talheres": [
        ("Cromado / Inox", "cromado", ("cromado",)),
        ("Dourado", "dourado", ("dourado",)),
        ("Bicolor", "bicolor", ("bicolor",)),
        ("Preto e Verde", "cores", ("preto", "verde")),
    ],
}

TIPOS_LOJA = {
    "varejo": "Varejo",
    "atacado": "Atacado",
    "restaurante": "Restaurante / Bar",
    "outro": "Outro",
}


def _opcoes(*itens):
    return [{"texto": texto, "valor": valor} for texto, valor in itens]


def _catalogos(texto="Qual catálogo você deseja ver?"):
    return {
        "tipo": "menu",
        "texto": texto,
        "opcoes": _opcoes(
            ("Cozinha e decoração", "cozinha"),
            ("Talheres", "talheres"),
            ("Pesquisar produto", "pesquisar"),
            ("Falar com atendente", "atendente"),
        ),
    }



def _menu_tipo_loja(texto):
    return {
        "tipo": "menu", "texto": texto,
        "opcoes": _opcoes(
            ("Varejo", "varejo"),
            ("Atacado", "atacado"),
            ("Restaurante / Bar", "restaurante"),
            ("Outro tipo", "outro"),
        ),
    }


def _menu_filtros(catalogo):
    opcoes = [(texto, f"f:{valor}") for texto, valor, _ in FILTROS[catalogo]]
    opcoes.append(("Ver tudo", "f:todos"))
    return {
        "tipo": "menu",
        "texto": "Quer filtrar por qual tipo?",
        "opcoes": _opcoes(*opcoes),
    }


def _filtrar(catalogo, filtro):
    if filtro == "todos":
        return buscar_produtos(catalogo)

    for _, valor, palavras in FILTROS[catalogo]:
        if valor == filtro:
            return buscar_produtos(catalogo, palavras)

    return buscar_produtos(catalogo)


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
    codigo = codigo.upper()
    return next((p for p in buscar_produtos(catalogo) if p["codigo"] == codigo), None)


def responder(mensagem, estado, cliente_existente=None, cadastro_pendente=False):
    """Decide todo o fluxo e atualiza o estado da sessão."""
    texto = str(mensagem or "").strip()
    normalizado = texto.lower()
    etapa = estado.get("etapa", "inicio")

    # 1) Começo da conversa
    if etapa == "inicio":
        if normalizado not in SAUDACOES:
            return {
                "tipo": "texto",
                "texto": "Para iniciar o atendimento, escreva 'oi'."
            }

        estado["etapa"] = "cadastro"
        return {
            "tipo": "menu",
            "texto": "Olá! 👋 Bem-vindo ao atendimento BM36. Você já é cadastrado?",
            "opcoes": _opcoes(
                ("Sim, já sou cliente", "sim"),
                ("Ainda não sou cliente", "nao"),
                ("Quero ver produtos", "produtos")
            )
        }

    # 2) Cadastro existente ou novo
    if etapa == "cadastro":
        if normalizado == "sim":
            estado["etapa"] = "documento_cliente"
            return {
                "tipo": "texto",
                "texto": "Informe seu CNPJ para localizar o cadastro."
            }

        if normalizado in {"nao", "não"}:
            estado["etapa"] = "documento_novo"
            return {
                "tipo": "texto",
                "texto": "Vamos fazer seu cadastro. Informe seu CNPJ."
            }

        if normalizado == "produtos":
            estado["etapa"] = "catalogos"
            return _catalogos()

        return {
            "tipo": "texto",
            "texto": "Escolha uma das opções disponíveis."
        }

    # 3) CNPJ
    if etapa in {"documento_cliente", "documento_novo"}:
        documento = _documento_valido(texto)

        if not documento:
            return {
                "tipo": "texto",
                "texto": "CNPJ inválido. Confira os 14 dígitos e digite novamente."
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
                f"Cadastro localizado! Seja bem-vindo, {cliente_existente}. selecione uma opção."
            )

        estado["documento"] = documento
        estado["etapa"] = "nome"

        if etapa == "documento_cliente":
            return {
                "tipo": "texto",
                "texto": (
                    "Não achei esse CNPJ. Vamos fazer seu cadastro. "
                    "Informe o nome ou a razão social da empresa."
                )
            }

        return {
            "tipo": "texto",
            "texto": "Informe seu nome ou a razão social da empresa."
        }

    # 4) Nome
    if etapa == "nome":
        nome = _texto_valido(texto, 2, 120)

        if not nome:
            return {
                "tipo": "texto",
                "texto": "Informe um nome ou razão social válido (sem símbolos como < > { })."
            }

        estado.update(nome=nome, etapa="tipo_loja")
        return _menu_tipo_loja("Qual é o tipo da sua loja?")

    # 5) Tipo de loja
    if etapa == "tipo_loja":
        if normalizado in {"varejo", "atacado", "restaurante"}:
            estado.update(tipo_loja=TIPOS_LOJA[normalizado], etapa="confirmar")
            return _menu_confirmar(estado)

        if normalizado == "outro":
            estado["etapa"] = "tipo_outro"
            return {
                "tipo": "texto",
                "texto": "Qual é o tipo da sua loja? Escreva em poucas palavras."
            }

        return _menu_tipo_loja("Escolha uma das opções abaixo.")

    if etapa == "tipo_outro":
        tipo = _texto_valido(texto, 2, 40)

        if not tipo:
            return {
                "tipo": "texto",
                "texto": "Escreva o tipo da sua loja (2 a 40 caracteres, sem símbolos)."
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
                "texto": "Sem problemas. Informe novamente o seu CNPJ."
            }

        return _menu_confirmar(estado)

    # 6) Escolher catálogo ou pesquisar
    if etapa in {"catalogos", "catalogo", "filtro"}:

        if normalizado == "pesquisar":
            estado["etapa"] = "pesquisar_produto"
            return {
                "tipo": "texto",
                "texto": (
                    "🔎 Digite o nome ou o código do produto que deseja encontrar."
                )
            }

        if normalizado in FILTROS:
            estado.update(catalogo=normalizado, etapa="filtro")
            return _menu_filtros(normalizado)

        # 7) Aplicar filtro do catálogo
        if normalizado.startswith("f:") and estado.get("catalogo"):
            catalogo = estado["catalogo"]
            produtos = _filtrar(catalogo, normalizado[2:])

            if not produtos:
                return {
                    "tipo": "texto",
                    "texto": "Não encontrei produtos nesse filtro."
                }

            estado["etapa"] = "catalogo"
            return {
                "tipo": "produtos",
                "texto": f"Encontrei {len(produtos)} produtos.",
                "produtos": produtos,
                "opcoes": _opcoes(
                    ("Outro filtro", f"filtros:{catalogo}"),
                    ("Pesquisar produto", "pesquisar"),
                    ("Ver outro catálogo", "produtos"),
                    ("Falar com atendente", "atendente")
                )
            }

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
            return {
                "tipo": "atendente",
                "texto": "Seu atendimento foi encaminhado para a equipe comercial.",
                "acao": "registrar_atendimento"
            }

        if normalizado.startswith("produto:"):
            produto = _produto_por_codigo(
                estado.get("catalogo", ""),
                normalizado.split(":", 1)[1]
            )

            if not produto:
                return {
                    "tipo": "texto",
                    "texto": "Não encontrei esse produto no catálogo atual."
                }

            estado.update(produto=produto, etapa="atendente")
            return {
                "tipo": "atendente",
                "texto": (
                    f"Ótima escolha: {produto['nome']}. "
                    "Vou encaminhar você a um atendente."
                ),
                "acao": "registrar_atendimento"
            }

        return {
            "tipo": "texto",
            "texto": "Use os botões disponíveis para continuar."
        }

    # 8) Pesquisar produto pelo nome ou código
    if etapa == "pesquisar_produto":
        if normalizado in {"voltar", "produtos"}:
            estado["etapa"] = "catalogos"
            return _catalogos()

        if normalizado == "atendente":
            estado["etapa"] = "atendente"
            return {
                "tipo": "atendente",
                "texto": "Seu atendimento foi encaminhado para a equipe comercial.",
                "acao": "registrar_atendimento"
            }

        produtos = pesquisar_produtos(texto)

        if not produtos:
            return {
                "tipo": "texto",
                "texto": (
                    "Não encontrei produtos com esse nome ou código. "
                    "Tente pesquisar de outra forma ou digite 'produtos' "
                    "para voltar ao catálogo."
                )
            }

        estado["etapa"] = "catalogo"

        return {
            "tipo": "produtos",
            "texto": f"Encontrei {len(produtos)} produto(s) para sua pesquisa.",
            "produtos": produtos,
            "opcoes": _opcoes(
                ("Pesquisar outro produto", "pesquisar"),
                ("Ver catálogos", "produtos"),
                ("Falar com atendente", "atendente")
            )
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
            )
        }

    # 10) Recuperação do fluxo
    estado["etapa"] = "inicio"
    return {
        "tipo": "texto",
        "texto": "Vamos recomeçar. Escreva 'oi'."
    }
