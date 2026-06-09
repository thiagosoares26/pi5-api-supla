import asyncio
import random

from fastapi import FastAPI
from datetime import date

from app.schemas import AITurnRequest, TurnPhase
from app.logic import choose_setup, choose_turn

app = FastAPI(
  title="Supla - O Jogador Inteligente",
  description="API do Supla, para o PI5",
  version="0.1.0"
)

@app.get("/health")
async def health():
  return date.today()

@app.post("/move")
async def move(body: AITurnRequest):
  """
  Endpoint principal chamado pelo orquestrador de partidas. 
  
  Recebe o estado completo de um turno da partida e devolve a jogada escolhida.
  """
  if body.turn_phase == TurnPhase.SETUP:
    return choose_setup(body.board)
  else:
    jogada = choose_turn(body.board, int(body.your_team))
    return jogada