# Conan Server Status - Scripts de Administração e Diagnóstico

Esta pasta contém utilitários administrativos desenvolvidos para auxiliar no diagnóstico de RCON, gerenciamento de banco de dados (`game.db`) e tarefas de manutenção do servidor Conan Exiles.

## ⚠️ Requisitos

Antes de executar qualquer script, certifique-se de estar no diretório raiz do projeto e com o ambiente virtual ativado:

```bash
source venv/bin/activate
```

---

## 🛠️ Scripts de Diagnóstico RCON

Estes scripts testam a conectividade RCON com os servidores configurados no `config.py`.

### 1. `test_rcon.py`
Conecta ao **primeiro servidor** configurado, envia o comando `ListPlayers` e exibe a resposta para validar a conexão.

```bash
python3 scripts/test_rcon.py
```

### 2. `diagnose_rcon.py`
Teste detalhado de conexão RCON com diagnóstico de erros (porta, senha, falha de autenticação ou firewall).

```bash
python3 scripts/diagnose_rcon.py
```

---

## 🗃️ Utilitários de Banco de Dados (`game.db`)

### 3. `transfer_player_assets.py`
Transfere a propriedade de construções, bancadas, baús e lacaios (thralls/pets) de um jogador/clã de origem para outro de destino no `game.db`. Suporta simulação (`--dry-run`) e aplicação segura com backup automático (`--apply`).

```bash
# Simular a transferência sem modificar o banco
python3 scripts/transfer_player_assets.py --source "NomeOrigem" --dest "NomeDestino" --dry-run

# Aplicar a transferência com backup automático (.bak)
python3 scripts/transfer_player_assets.py --source "NomeOrigem" --dest "NomeDestino" --apply
```

### 4. `recalculate_ranking.py`
Recalcula e recalibra as pontuações e rankings de PvP na base do Killfeed (`ranking.db`).

```bash
python3 scripts/recalculate_ranking.py
```

### 5. `extract_structures.py`
Extrai posições e contagem de peças de estruturas do `game.db` para exportação e visualização no mapa.

```bash
python3 scripts/extract_structures.py
```

---

## ⚡ Pasta `benchmarks/`

A pasta [`scripts/benchmarks/`](file:///home/eduardoh@unisc.br/Pessoal/1_Projetos_Desenvolvimento/conanserverstatus/scripts/benchmarks/) contém scripts de perfilamento, testes de estresse e verificações de desempenho desenvolvidos durante as otimizações do bot.
