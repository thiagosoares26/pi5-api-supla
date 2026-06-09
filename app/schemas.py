from enum import IntEnum, Enum
from typing import Optional, List
from pydantic import BaseModel, Field

class TeamID(IntEnum):
    """Identificador do time."""
    TURING = 1       # professores CLARO e REY
    LOVELACE = 2     # professoras KARIN e BEATRIZ

class TurnPhase(str, Enum):
    """Fase do turno."""
    SETUP = "setup_placement"        # posicionamento inicial
    PLAYER_TURN = "player_turn"      # turno de jogo
    
# ── Celula do tabuleiro ────────────────────────────────

class Cell(BaseModel):
    """
    Cada casa do tabuleiro 5x5.

    - level: altura da construcao (0 a 4).
             0 = terreno vazio, 3 = vitoria ao entrar, 4 = graduada (bloqueada).
    - professor: nome do professor ocupando a casa, ou null se vazia.
    """
    level: int = Field(ge=0, le=4)
    professor: Optional[str] = None

# ── Posicao no tabuleiro ───────────────────────────────

class Position(BaseModel):
    """Coordenada (row, col) no tabuleiro 5x5."""
    row: int = Field(ge=0, le=4)
    col: int = Field(ge=0, le=4)

class AITurnRequest(BaseModel):
  """
  Payload que foi enviado pelo orquestrador de partidas.
  """
  game_id: str
  turn_number: int
  turn_phase: TurnPhase
  your_team: TeamID
  board: List[List[Cell]]
  professor_to_place: Optional[str] = Field(default=None) # preenchido só no setup
  
class SetupResponse(BaseModel):
  """Resposta na fase de posicionamento: onde colocar o professor."""
  row: int = Field(ge=0, le=4)
  col: int = Field(ge=0, le=4)
  
class PlayerTurnResponse(BaseModel):
    """
    Resposta na fase de turno de jogo.

    - professor: qual professor mover (ex: "CLARO")
    - move_to: para qual casa mover
    - mentor_at: qual casa adjacente ao destino recebe mentoria (+1 nivel).
                 Pode ser omitido APENAS em jogada de vitoria (destino nivel 3).
    """
    professor: str
    move_to: Position
    mentor_at: Optional[Position] = None