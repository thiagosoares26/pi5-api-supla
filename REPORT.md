# REPORT — PI5


## 1. Visão geral

Este projeto implementa um **jogador automático (bot)** para um jogo de tabuleiro de construção e promoção. Duas equipes de professores disputam quem leva um de seus alunos ao nível 3. A cada turno, um jogador move um professor e aumenta o nivel de um aluno; vence quem primeiro escala até vitória, e perde quem fica sem jogadas legais.

A aplicação é um **serviço** que recebe o estado do tabuleiro vindo de um servidor-árbitro e devolve a jogada escolhida. Toda a inteligência fica concentrada no módulo `logic.py`, que combina um **filtro de restrições (CSP)** para gerar apenas jogadas legais com uma **busca adversarial Minimax (formulação Negamax) com poda alpha-beta** para escolher a melhor delas.

---

## 2. Regras do jogo 

- Tabuleiro **5×5**; cada casa tem um **nível** de `0` a `4`.
- Cada equipe controla **2 professores**:
  - **Equipe 1 — Turing:** `CLARO`, `REY`
  - **Equipe 2 — Lovelace:** `KARIN`, `BEATRIZ`
- Um turno = **mover** um professor para uma casa adjacente (8 direções) **+ construir** um andar ("mentoria") numa casa adjacente ao destino.
- Restrições de movimento:
  - não entrar em casa ocupada;
  - não entrar em casa de nível `4` (cúpula);
  - subir **no máximo um nível** por movimento.
- **Vitória:** mover um professor para uma casa de **nível 3** (esse lance não exige construção).
- **Derrota:** ficar **sem jogadas legais** no próprio turno.

---

## 3. Estrutura da aplicação

A aplicação segue uma separação clara entre **contrato de dados**, **lógica de decisão** e **camada de serviço**:

### 3.1. Camada de dados — `schemas.py`

Define os modelos Pydantic que formam o **contrato** entre o servidor do jogo e o nosso bot:

| Modelo | Campos | Papel |
|---|---|---|
| `Cell` | `level`, `professor` | Uma casa do tabuleiro |
| `Position` | `row`, `col` | Uma coordenada |
| `SetupResponse` | `row`, `col` | Resposta da fase de posicionamento |
| `PlayerTurnResponse` | `professor`, `move_to`, `mentor_at` | Resposta de um turno |

O uso de Pydantic garante **validação automática** dos dados recebidos e enviados, evitando que estados malformados cheguem à lógica.

### 3.2. Camada de decisão — `logic.py`

É o coração do projeto. Está organizado em camadas, das primitivas à interface pública:

| Camada | Funções | Responsabilidade |
|---|---|---|
| Utilitários | `vizinhas`, `localizar`, `mapear_professores`, `equipe_adversaria` | Navegação no tabuleiro |
| Filtro CSP | `jogadas_validas`, `contar_jogadas`, `ordenar_jogadas` | Gerar, contar e ordenar jogadas legais |
| Simulação | `simular_jogada` | Aplicar uma jogada sem mutar o estado original |
| Avaliação | `avaliar` | Atribuir nota numérica a um estado |
| Busca | `busca` | Negamax + poda alpha-beta |
| Interface | `choose_setup`, `choose_turn` | Pontos de entrada chamados pelo jogo |

### 3.3. Camada de serviço (API)

Uma camada de API expõe os *endpoints* consumidos pelo servidor-árbitro. O fluxo de comunicação a cada rodada é:

```
Servidor-árbitro  ──(estado do tabuleiro)──►  API  ──►  logic.choose_setup / choose_turn
                  ◄──────(jogada escolhida)──  API  ◄──  SetupResponse / PlayerTurnResponse
```

A API é **fina de propósito**: ela apenas valida a entrada (via schemas) e delega a decisão para `logic.py`. Isso mantém a inteligência isolada, fácil de testar e independente do protocolo de transporte.

---

## 4. Jogador Inteligente — Estratégia

Esta seção detalha **como construímos** o jogador, **quais algoritmos** usamos e **como o testamos**.

### 4.1. Filosofia geral

Encaramos o problema em duas etapas:

1. **O que é possível jogar?** — geramos apenas as jogadas que respeitam todas as regras.
2. **O que é melhor jogar?** — simulamos o jogo alguns lances à frente assumindo que o adversário também joga bem.


### 4.2. Geração de jogadas como CSP

A função `jogadas_validas` percorre cada professor da equipe e, para cada casa de destino adjacente, aplica as **restrições** do jogo como filtros sucessivos:

- destino livre (`professor is None`);
- destino abaixo da cúpula (`level < 4`);
- subida de no máximo um nível (`level <= altura_atual + 1`).

Para cada destino válido, geramos:

- uma **jogada de vitória** (sem construção), se o destino for nível 3; ou
- uma jogada para **cada casa de construção legal** adjacente ao destino, incluindo a casa de origem (que fica livre após o movimento).

Tratar a geração como CSP garante, por construção, que **nenhuma jogada ilegal entra na árvore de busca** — o que simplifica o restante do código e elimina uma classe inteira de bugs.

### 4.3. Avaliação heurística do estado

Como não é viável buscar até o fim do jogo, usamos uma **função de avaliação** (`avaliar`) que estima a qualidade de um estado intermediário do ponto de vista de uma equipe. Ela combina cinco fatores ponderados:

| Fator | Peso | Intuição estratégica |
| `vitoria` | `10000` | Estados terminais dominam qualquer outra consideração |
| `minha_altura` | `+22` | Subir os próprios professores aproxima da vitória |
| `altura_adversario` | `-28` | Conter a subida do oponente (peso maior → postura defensiva) |
| `controle_centro` | `+11` | O centro oferece mais mobilidade e mais alvos de construção |
| `mobilidade` | `+1` | Ter mais jogadas que o oponente é vantagem posicional |
| `potencial_subida` | `+4` | Estar ao lado de uma casa um nível acima é "ameaça de subida" |

A escolha de `altura_adversario` (−28) **maior em módulo** que `minha_altura` (+22) torna o bot levemente **defensivo**: ele dá mais valor a impedir a escalada do oponente do que à própria. A distância ao centro é medida pela **distância de Manhattan** ao centro do tabuleiro.

### 4.4. Algoritmo de busca: Minimax / Negamax com poda alpha-beta

O motor de decisão (`busca`) é um **Minimax** implementado na forma **Negamax**: em vez de duplicar a lógica de "maximizar" e "minimizar", avaliamos sempre do ponto de vista de quem joga e **invertemos o sinal** a cada nível de recursão (`valor = -busca(...)`). Isso reduz o código pela metade sem mudar o resultado.

Sobre o Minimax aplicamos **poda alpha-beta**, que descarta ramos comprovadamente piores que uma alternativa já encontrada. 

Cada nó da busca trata, em ordem, os casos terminais e o caso recursivo:

1. **sem jogadas** → a equipe da vez perde (`-vitoria`);
2. **vitória imediata disponível** → vence (`+vitoria`);
3. **profundidade zero** → retorna `avaliar(...)`;
4. **caso geral** → expande os lances e aplica alpha-beta.

### 4.5. Otimizações de desempenho

- **Ordenação de jogadas** (`ordenar_jogadas`): testamos primeiro as vitórias e as subidas mais altas. A poda alpha-beta é dramaticamente mais eficaz quando as melhores jogadas vêm primeiro.
- **Atalho de vitória imediata** em `choose_turn`: se existe um lance que vence na hora, jogamos sem nem abrir a árvore (custo O(1) por jogada).
- **Cópia rasa em vez de `deepcopy`** (`simular_jogada`): recriamos apenas as referências das casas alteradas, em vez de copiar todo o tabuleiro a cada simulação.
- **Cache de posições** (`mapear_professores`): varremos o tabuleiro uma única vez por estado em vez de procurar cada professor repetidamente.

### 4.6. Fase de posicionamento (`choose_setup`)

No setup inicial, escolhemos uma casa **livre e de nível 0**, priorizando o **miolo do tabuleiro** (linhas/colunas 1–3). A motivação é estratégica: posições centrais maximizam a mobilidade futura e o número de alvos de construção, fatores que a própria função de avaliação valoriza.

## 6. Conclusão

O jogador combina duas técnicas clássicas de IA de forma complementar: um **filtro CSP** que garante legalidade por construção e um **Minimax com poda alpha-beta** que escolhe a jogada com melhor perspectiva de algumas rodadas à frente, guiado por uma função de avaliação ponderada e levemente defensiva. As otimizações (ordenação de jogadas, atalho de vitória, cópia rasa e cache de posições) e a profundidade configurável equilibram **força de jogo** e **tempo de resposta**, deixando o bot competitivo e com caminho claro de evolução.
