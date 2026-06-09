# app/logic.py
import math
import random
from typing import Optional

from app.schemas import Cell, Position, SetupResponse, PlayerTurnResponse

GRID = 5
ALTURA_VITORIA = 3   # subir até este nível vence o jogo
ALTURA_MAXIMA = 4    # cúpula: ninguém pode ocupar nem construir acima

# Professores controlados por cada equipe
PROFS_POR_EQUIPE = {
    1: ("CLARO", "REY"),       # Turing
    2: ("KARIN", "BEATRIZ"),   # Lovelace
}

# Pesos da função de avaliação
PESOS = {
    "vitoria": 10_000.0,
    "minha_altura": 22.0,
    "altura_adversario": -28.0,
    "controle_centro": 11.0,
    "mobilidade": 1.0,
    "potencial_subida": 4.0,   # estar ao lado de uma casa um nível acima é bom
}


# =========================================================
# UTILITÁRIOS DE TABULEIRO
# =========================================================
def equipe_adversaria(equipe: int) -> int:
    return 2 if equipe == 1 else 1


def vizinhas(linha: int, coluna: int):
    """Gera as casas adjacentes (8 direções) que ficam dentro do grid."""
    for dl in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dl == 0 and dc == 0:
                continue
            nl, nc = linha + dl, coluna + dc
            if 0 <= nl < GRID and 0 <= nc < GRID:
                yield nl, nc


def localizar(tabuleiro: list[list[Cell]], prof: str) -> Optional[tuple[int, int]]:
    """Posição (linha, coluna) de um único professor, com saída antecipada."""
    for l in range(GRID):
        for c in range(GRID):
            if tabuleiro[l][c].professor == prof:
                return (l, c)
    return None


def mapear_professores(tabuleiro: list[list[Cell]]) -> dict[str, tuple[int, int]]:
    """Varre o tabuleiro UMA vez e devolve {nome: (linha, coluna)}."""
    posicoes: dict[str, tuple[int, int]] = {}
    for l in range(GRID):
        for c in range(GRID):
            prof = tabuleiro[l][c].professor
            if prof is not None:
                posicoes[prof] = (l, c)
    return posicoes


# =========================================================
# FILTRO CSP: GERAÇÃO DE JOGADAS LEGAIS
# =========================================================
def jogadas_validas(
    tabuleiro: list[list[Cell]],
    equipe: int,
    posicoes: Optional[dict[str, tuple[int, int]]] = None,
) -> list[PlayerTurnResponse]:
    """Todas as jogadas legais da equipe (mover + construir / mover para vencer)."""
    if posicoes is None:
        posicoes = mapear_professores(tabuleiro)

    jogadas: list[PlayerTurnResponse] = []
    for prof in PROFS_POR_EQUIPE[equipe]:
        origem = posicoes.get(prof)
        if origem is None:
            continue
        ol, oc = origem
        altura_atual = tabuleiro[ol][oc].level

        for dl, dc in vizinhas(ol, oc):
            destino = tabuleiro[dl][dc]

            # Restrições de movimento (CSP)
            if destino.professor is not None:
                continue
            if destino.level >= ALTURA_MAXIMA:
                continue
            if destino.level > altura_atual + 1:
                continue

            # Subir ao nível de vitória encerra a jogada (não constrói)
            if destino.level == ALTURA_VITORIA:
                jogadas.append(PlayerTurnResponse(
                    professor=prof,
                    move_to=Position(row=dl, col=dc),
                ))
                continue

            # Jogada normal: depois de mover, constrói (mentoria) numa casa
            # adjacente ao destino. A própria origem é um alvo válido.
            for ml, mc in vizinhas(dl, dc):
                mentoria = tabuleiro[ml][mc]
                eh_origem = (ml, mc) == (ol, oc)
                if (mentoria.professor is None or eh_origem) and mentoria.level < ALTURA_MAXIMA:
                    jogadas.append(PlayerTurnResponse(
                        professor=prof,
                        move_to=Position(row=dl, col=dc),
                        mentor_at=Position(row=ml, col=mc),
                    ))
    return jogadas


def contar_jogadas(
    tabuleiro: list[list[Cell]],
    equipe: int,
    posicoes: Optional[dict[str, tuple[int, int]]] = None,
) -> int:
    """Conta jogadas legais sem instanciar Pydantic (usado no fator mobilidade)."""
    if posicoes is None:
        posicoes = mapear_professores(tabuleiro)

    total = 0
    for prof in PROFS_POR_EQUIPE[equipe]:
        origem = posicoes.get(prof)
        if origem is None:
            continue
        ol, oc = origem
        altura_atual = tabuleiro[ol][oc].level

        for dl, dc in vizinhas(ol, oc):
            destino = tabuleiro[dl][dc]
            if destino.professor is not None:
                continue
            if destino.level >= ALTURA_MAXIMA:
                continue
            if destino.level > altura_atual + 1:
                continue
            if destino.level == ALTURA_VITORIA:
                total += 1
                continue
            for ml, mc in vizinhas(dl, dc):
                mentoria = tabuleiro[ml][mc]
                eh_origem = (ml, mc) == (ol, oc)
                if (mentoria.professor is None or eh_origem) and mentoria.level < ALTURA_MAXIMA:
                    total += 1
    return total


def ordenar_jogadas(
    tabuleiro: list[list[Cell]], jogadas: list[PlayerTurnResponse]
) -> list[PlayerTurnResponse]:
    """Heurística barata de ordenação: melhora muito a poda alpha-beta.

    Tenta primeiro as jogadas de vitória e as que sobem mais alto.
    """
    def prioridade(j: PlayerTurnResponse):
        destino = tabuleiro[j.move_to.row][j.move_to.col]
        return (j.mentor_at is None, destino.level)

    return sorted(jogadas, key=prioridade, reverse=True)


# =========================================================
# SIMULAÇÃO DE JOGADA
# =========================================================
def simular_jogada(
    tabuleiro: list[list[Cell]], jogada: PlayerTurnResponse
) -> list[list[Cell]]:
    """Aplica a jogada numa cópia rasa do tabuleiro (sem deepcopy)."""
    novo = [linha[:] for linha in tabuleiro]  # nova matriz de referências

    # 1. Tira o professor da casa de origem
    origem = localizar(tabuleiro, jogada.professor)
    if origem:
        ol, oc = origem
        novo[ol][oc] = Cell(level=tabuleiro[ol][oc].level, professor=None)

    # 2. Coloca o professor na casa de destino
    dl, dc = jogada.move_to.row, jogada.move_to.col
    novo[dl][dc] = Cell(level=tabuleiro[dl][dc].level, professor=jogada.professor)

    # 3. Constrói um andar (mentoria), se houver
    if jogada.mentor_at:
        ml, mc = jogada.mentor_at.row, jogada.mentor_at.col
        # usa o professor já presente em `novo` (a origem pode ter sido esvaziada)
        prof_na_casa = novo[ml][mc].professor
        novo[ml][mc] = Cell(level=tabuleiro[ml][mc].level + 1, professor=prof_na_casa)

    return novo


# =========================================================
# AVALIAÇÃO DE ESTADO
# =========================================================
def avaliar(tabuleiro: list[list[Cell]], equipe: int) -> float:
    """Pontua o tabuleiro do ponto de vista de `equipe` (quanto maior, melhor)."""
    adversario = equipe_adversaria(equipe)
    meus = PROFS_POR_EQUIPE[equipe]
    deles = PROFS_POR_EQUIPE[adversario]

    posicoes = mapear_professores(tabuleiro)
    score = 0.0

    for prof, (l, c) in posicoes.items():
        altura = tabuleiro[l][c].level

        # Se alguém já está no nível de vitória, o resultado está decidido
        if altura == ALTURA_VITORIA:
            return PESOS["vitoria"] if prof in meus else -PESOS["vitoria"]

        if prof in meus:
            score += altura * PESOS["minha_altura"]
            dist_centro = abs(l - 2) + abs(c - 2)
            score += (4 - dist_centro) * PESOS["controle_centro"]
            # potencial de subida: casa livre exatamente um nível acima
            for vl, vc in vizinhas(l, c):
                viz = tabuleiro[vl][vc]
                if viz.professor is None and viz.level == altura + 1 and viz.level < ALTURA_MAXIMA:
                    score += PESOS["potencial_subida"]
        elif prof in deles:
            score += altura * PESOS["altura_adversario"]

    # Fator de mobilidade (reaproveita o mapa de posições já calculado)
    score += (
        contar_jogadas(tabuleiro, equipe, posicoes)
        - contar_jogadas(tabuleiro, adversario, posicoes)
    ) * PESOS["mobilidade"]

    return score


# =========================================================
# MOTOR DE BUSCA (NEGAMAX + ALPHA-BETA)
# =========================================================
def busca(
    tabuleiro: list[list[Cell]],
    profundidade: int,
    alpha: float,
    beta: float,
    equipe: int,
) -> float:
    """Negamax com poda alpha-beta, sempre do ponto de vista de quem joga (`equipe`)."""
    jogadas = jogadas_validas(tabuleiro, equipe)

    # Sem jogadas legais = a equipe da vez perde
    if not jogadas:
        return -PESOS["vitoria"]

    # Vitória imediata disponível (jogadas de vitória não constroem)
    for jogada in jogadas:
        if jogada.mentor_at is None:
            return PESOS["vitoria"]

    if profundidade == 0:
        return avaliar(tabuleiro, equipe)

    adversario = equipe_adversaria(equipe)
    melhor = -math.inf
    for jogada in ordenar_jogadas(tabuleiro, jogadas):
        filho = simular_jogada(tabuleiro, jogada)
        valor = -busca(filho, profundidade - 1, -beta, -alpha, adversario)
        if valor > melhor:
            melhor = valor
        if melhor > alpha:
            alpha = melhor
        if alpha >= beta:
            break
    return melhor


# =========================================================
# INTERFACE DO BOT (nomes obrigatórios)
# =========================================================
def choose_setup(board: list[list[Cell]]) -> SetupResponse:
    """Fase de posicionamento: prioriza o miolo do tabuleiro."""
    livres = [
        (l, c)
        for l in range(GRID)
        for c in range(GRID)
        if board[l][c].level == 0 and board[l][c].professor is None
    ]
    centro = [(l, c) for l, c in livres if 1 <= l <= 3 and 1 <= c <= 3]
    linha, coluna = random.choice(centro or livres)
    return SetupResponse(row=linha, col=coluna)


def choose_turn(board: list[list[Cell]], team_id: int) -> Optional[PlayerTurnResponse]:
    """Decide a melhor jogada via filtro CSP + negamax com poda alpha-beta."""
    jogadas = jogadas_validas(board, team_id)
    if not jogadas:
        return None

    # 1) Vitória imediata, se existir — resposta O(1) por jogada
    for jogada in jogadas:
        if jogada.mentor_at is None:
            return jogada

    # 2) Busca em profundidade.
    #    2 = mesma profundidade do bot original (rápido e seguro).
    #    Suba para 3 SE o limite de tempo da partida permitir — a ordenação de
    #    jogadas torna isso viável, mas com Pydantic real pode levar alguns segundos.
    PROFUNDIDADE = 2
    adversario = equipe_adversaria(team_id)

    melhor_jogada: Optional[PlayerTurnResponse] = None
    melhor_score = -math.inf
    alpha, beta = -math.inf, math.inf

    for jogada in ordenar_jogadas(board, jogadas):
        filho = simular_jogada(board, jogada)
        score = -busca(filho, PROFUNDIDADE - 1, -beta, -alpha, adversario)
        if score > melhor_score:
            melhor_score = score
            melhor_jogada = jogada
        if melhor_score > alpha:
            alpha = melhor_score

    return melhor_jogada or random.choice(jogadas)
