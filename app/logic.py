# app/logic.py
import random
import math
from typing import Optional

from app.schemas import Cell, Position, SetupResponse, PlayerTurnResponse

BOARD_SIZE = 5

# Professores de cada time
TEAM_PROFESSORS = {
    1: ["CLARO", "REY"],       # Turing
    2: ["KARIN", "BEATRIZ"],   # Lovelace
}

# Pesos da Função de Avaliação
WEIGHTS = {
    "win_move": 10000.0,
    "my_height": 22.0,         
    "opp_height": -28.0,       
    "center_control": 11.0,    
    "mobility": 1.0            
}

# =========================================================
# MÓDULO 1: FILTRO CSP (Satisfação de Restrições)
# =========================================================
def adjacent_cells(row: int, col: int) -> list[tuple[int, int]]:
    """Retorna todas as casas vizinhas (incluindo diagonais) dentro do grid."""
    cells = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = row + dr, col + dc
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                cells.append((nr, nc))
    return cells

def find_professor(board: list[list[Cell]], name: str) -> Optional[tuple[int, int]]:
    """Encontra a posição (row, col) de um professor no tabuleiro."""
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c].professor == name:
                return (r, c)
    return None

def choose_setup(board: list[list[Cell]]) -> SetupResponse:
    """Fase de posicionamento: escolhe o centro ou adjacências aleatórias."""
    candidates = [
        (r, c)
        for r in range(BOARD_SIZE)
        for c in range(BOARD_SIZE)
        if board[r][c].level == 0 and board[r][c].professor is None
    ]
    # Tenta priorizar o centro no setup
    center_candidates = [(r, c) for r, c in candidates if 1 <= r <= 3 and 1 <= c <= 3]
    row, col = random.choice(center_candidates if center_candidates else candidates)
    return SetupResponse(row=row, col=col)

def get_legal_moves(board: list[list[Cell]], team_id: int) -> list[PlayerTurnResponse]:
    """Gera todos os movimentos legais para a equipe atual (Filtro CSP)."""
    legal_moves = []
    
    for professor in TEAM_PROFESSORS[team_id]:
        pos = find_professor(board, professor)
        if pos is None:
            continue

        cur_row, cur_col = pos
        cur_level = board[cur_row][cur_col].level

        for dst_row, dst_col in adjacent_cells(cur_row, cur_col):
            dst_cell = board[dst_row][dst_col]

            # Restrições (CSP)
            if dst_cell.professor is not None: continue
            if dst_cell.level == 4: continue
            if dst_cell.level > cur_level + 1: continue

            # Se for vitória imediata (movimento para nível 3)
            if dst_cell.level == 3:
                legal_moves.append(PlayerTurnResponse(
                    professor=professor,
                    move_to=Position(row=dst_row, col=dst_col)
                ))
                continue

            # Movimentos normais que exigem mentoria (construção)
            for men_row, men_col in adjacent_cells(dst_row, dst_col):
                men_cell = board[men_row][men_col]
                is_source = (men_row, men_col) == (cur_row, cur_col)
                
                if (men_cell.professor is None or is_source) and men_cell.level < 4:
                    legal_moves.append(PlayerTurnResponse(
                        professor=professor,
                        move_to=Position(row=dst_row, col=dst_col),
                        mentor_at=Position(row=men_row, col=men_col)
                    ))
                    
    return legal_moves

def count_legal_moves(board: list[list[Cell]], team_id: int) -> int:
    """Contador de mobilidade otimizado para não instanciar objetos Pydantic."""
    count = 0
    for professor in TEAM_PROFESSORS[team_id]:
        pos = find_professor(board, professor)
        if pos is None: continue
        
        cur_row, cur_col = pos
        cur_level = board[cur_row][cur_col].level

        for dst_row, dst_col in adjacent_cells(cur_row, cur_col):
            dst_cell = board[dst_row][dst_col]
            if dst_cell.professor is not None: continue
            if dst_cell.level == 4: continue
            if dst_cell.level > cur_level + 1: continue

            if dst_cell.level == 3:
                count += 1
                continue

            for men_row, men_col in adjacent_cells(dst_row, dst_col):
                men_cell = board[men_row][men_col]
                is_source = (men_row, men_col) == (cur_row, cur_col)
                if (men_cell.professor is None or is_source) and men_cell.level < 4:
                    count += 1
    return count

def apply_move(board: list[list[Cell]], move: PlayerTurnResponse) -> list[list[Cell]]:
    """Simula um movimento via reatribuição explícita (Evita overhead de deepcopy)."""
    # Cópia rasa: cria uma nova matriz de referências, permitindo mutação isolada
    new_board = [row[:] for row in board] 

    # 1. Encontra e remove o professor da posição antiga
    old_pos = find_professor(board, move.professor)
    if old_pos:
        o_r, o_c = old_pos
        new_board[o_r][o_c] = Cell(level=board[o_r][o_c].level, professor=None)

    # 2. Move o professor para a nova posição
    n_r, n_c = move.move_to.row, move.move_to.col
    new_board[n_r][n_c] = Cell(level=board[n_r][n_c].level, professor=move.professor)

    # 3. Aplica a mentoria (constrói um andar), se houver
    if move.mentor_at:
        m_r, m_c = move.mentor_at.row, move.mentor_at.col
        curr_prof = new_board[m_r][m_c].professor # Usa o estado do new_board caso a célula seja a mesma de destino
        new_board[m_r][m_c] = Cell(level=board[m_r][m_c].level + 1, professor=curr_prof)

    return new_board

# =========================================================
# MÓDULO 2: AVALIAÇÃO DE ESTADO
# =========================================================
def evaluate_board(board: list[list[Cell]], team_id: int, opp_id: int) -> float:
    """Avalia o estado do tabuleiro usando os pesos definidos."""
    score = 0.0
    
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            cell = board[r][c]
            if cell.professor is None:
                continue

            # Verifica se alguém já venceu
            if cell.level == 3:
                return WEIGHTS["win_move"] if cell.professor in TEAM_PROFESSORS[team_id] else -WEIGHTS["win_move"]

            # Aplica pontuação de heurística posicional
            if cell.professor in TEAM_PROFESSORS[team_id]:
                score += cell.level * WEIGHTS["my_height"]
                # Distância de Manhattan do centro
                center_dist = abs(r - 2) + abs(c - 2)
                score += (4 - center_dist) * WEIGHTS["center_control"]
            elif cell.professor in TEAM_PROFESSORS[opp_id]:
                score += cell.level * WEIGHTS["opp_height"]

    # Fator de Mobilidade
    score += (count_legal_moves(board, team_id) - count_legal_moves(board, opp_id)) * WEIGHTS["mobility"]
    
    return score

# =========================================================
# MÓDULO 3: MOTOR MINIMAX
# =========================================================
def minimax(board: list[list[Cell]], depth: int, alpha: float, beta: float, is_maximizing: bool, team_id: int, opp_id: int) -> float:
    """Busca em profundidade com Alpha-Beta Pruning."""
    if depth == 0:
        return evaluate_board(board, team_id, opp_id)

    current_team = team_id if is_maximizing else opp_id
    legal_moves = get_legal_moves(board, current_team)
    
    # Condição de terminalidade natural (sem movimentos válidos)
    if not legal_moves:
        return -WEIGHTS["win_move"] if is_maximizing else WEIGHTS["win_move"]

    if is_maximizing:
        max_eval = -math.inf
        for move in legal_moves:
            simulated_board = apply_move(board, move)
            
            if move.mentor_at is None and simulated_board[move.move_to.row][move.move_to.col].level == 3:
                return WEIGHTS["win_move"]
                
            eval_score = minimax(simulated_board, depth - 1, alpha, beta, False, team_id, opp_id)
            max_eval = max(max_eval, eval_score)
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break
        return max_eval
    else:
        min_eval = math.inf
        for move in legal_moves:
            simulated_board = apply_move(board, move)
            
            if move.mentor_at is None and simulated_board[move.move_to.row][move.move_to.col].level == 3:
                return -WEIGHTS["win_move"]
                
            eval_score = minimax(simulated_board, depth - 1, alpha, beta, True, team_id, opp_id)
            min_eval = min(min_eval, eval_score)
            beta = min(beta, eval_score)
            if beta <= alpha:
                break
        return min_eval

def choose_turn(board: list[list[Cell]], team_id: int) -> Optional[PlayerTurnResponse]:
    """Decide a melhor jogada usando CSP (Filtro) e Minimax + Alpha-Beta."""
    opp_id = 2 if team_id == 1 else 1
    
    legal_moves = get_legal_moves(board, team_id)
    if not legal_moves:
        return None

    # Avaliação de vitória imediata antes de expandir a árvore O(1)
    for move in legal_moves:
        if move.mentor_at is None:
            return move

    # Inicia a busca Minimax
    SEARCH_DEPTH = 2 
    best_move = None
    best_score = -math.inf
    alpha = -math.inf
    beta = math.inf

    for move in legal_moves:
        simulated_board = apply_move(board, move)
        move_score = minimax(simulated_board, SEARCH_DEPTH - 1, alpha, beta, False, team_id, opp_id)
        
        if move_score > best_score:
            best_score = move_score
            best_move = move
            
        alpha = max(alpha, best_score)

    return best_move if best_move else random.choice(legal_moves)