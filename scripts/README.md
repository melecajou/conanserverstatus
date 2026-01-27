# Conan Server Status - Scripts de Diagnóstico e Auditoria

Esta pasta contém scripts utilitários desenvolvidos para ajudar administradores a diagnosticar problemas de conexão RCON, auditar o banco de dados do jogo (`game.db`) e gerenciar ativos "fantasmas" (objetos ou seguidores abandonados).

## ⚠️ Requisitos

Antes de rodar qualquer script, certifique-se de estar no diretório raiz do projeto e com o ambiente virtual ativado:

```bash
cd /home/steam/bots/ConanServerStatus
source venv/bin/activate
```

---

## 🛠️ Scripts de Diagnóstico RCON

Estes scripts testam a conectividade com o servidor do jogo usando as credenciais do `config.py`.

### 1. `test_rcon.py`
Um teste simples de conexão. Conecta ao **primeiro servidor** listado no `config.py`, executa o comando `ListPlayers` e exibe a resposta crua.

**Uso:**
```bash
python3 scripts/test_rcon.py
```

### 2. `diagnose_rcon.py`
Uma versão mais detalhada do teste de conexão, projetada para identificar falhas de autenticação ou erros de rede. Tenta isolar se o problema é senha, porta ou firewall.

**Uso:**
```bash
python3 scripts/diagnose_rcon.py
```

---

## 🕵️‍♂️ Scripts de Auditoria de Banco de Dados

Estes scripts leem o arquivo `game.db` (SQLite) para encontrar informações que não estão disponíveis via RCON. Eles abrem o banco em **Modo Somente Leitura (`ro`)**, portanto são seguros para rodar com o servidor ligado.

**Nota:** Por padrão, eles buscam o arquivo `game_backup_1.db`. Use o argumento `--db` para especificar outro caminho.

### 3. `find_orphans.py`
Localiza objetos (bancadas, baús) e seguidores (thralls, pets) pertencentes a um Clã ou Jogador específico que não são peças de construção. Útil para limpar restos de bases deletadas.

**Uso:**
```bash
# Listar tudo (Objetos + Seguidores)
python3 scripts/find_orphans.py "Nome do Clã"

# Listar apenas Seguidores
python3 scripts/find_orphans.py "Nome do Clã" --thralls-only

# Usar outro banco de dados
python3 scripts/find_orphans.py "Nome do Jogador" --db "/caminho/para/game.db"
```

### 4. `map_assets.py` (Relatório Completo)
Gera um inventário completo e categorizado de tudo que um Clã ou Jogador possui no mapa. Diferencia claramente o que é "Objeto Placeable" do que é "Seguidor", decodificando nomes customizados.

**Uso:**
```bash
python3 scripts/map_assets.py "Nome do Clã ou Jogador"
```

### 5. `list_inactive_assets.py` (Varredor de Inatividade)
O script mais poderoso para limpeza. Ele identifica Clãs ou Jogadores Solo que não logaram nos últimos X dias e lista **apenas** os ativos (bancadas, baús, thralls) que eles deixaram para trás, ignorando as estruturas de construção.

**Uso:**
```bash
# Listar inativos há mais de 15 dias (padrão)
python3 scripts/list_inactive_assets.py

# Listar inativos há mais de 30 dias
python3 scripts/list_inactive_assets.py --days 30
```

### 6. `list_thralls_advanced.py`
Focado exclusivamente em encontrar e listar todos os seguidores (Thralls/Pets) do servidor ou de um alvo específico, usando uma técnica avançada de decodificação de IDs hexadecimais na tabela de propriedades.

**Uso:**
```bash
# Listar TODOS os seguidores do servidor
python3 scripts/list_thralls_advanced.py

# Filtrar por um clã específico
python3 scripts/list_thralls_advanced.py "Nome do Clã"
```
