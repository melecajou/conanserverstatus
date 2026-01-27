# Relatório de Análise de Estrutura: Conan Exiles `game.db`

Este documento detalha as descobertas sobre a estrutura do banco de dados SQLite `game.db`, especificamente no que tange ao rastreamento de itens, inventários e propriedade.

## 1. Tabelas Principais

A estrutura utiliza um sistema de IDs únicos para vincular objetos espalhados por diferentes tabelas:

*   **`characters`**: Contém os dados dos jogadores.
    *   `id`: ID numérico único do personagem.
    *   `char_name`: Nome visível do personagem.
    *   `guild`: ID da guilda (clã) à qual o jogador pertence.
*   **`guilds`**: Contém os dados dos clãs.
    *   `guildId`: ID numérico único do clã.
    *   `name`: Nome do clã.
*   **`item_inventory`**: A tabela central de itens.
    *   `template_id`: O ID do item (ex: 11066 para Moedas de Ouro).
    *   `owner_id`: O ID do dono (pode ser um Personagem ou um Objeto/Baú).
    *   `inv_type`: Define a categoria do inventário.
    *   `data`: Um BLOB binário que contém a quantidade e metadados.
*   **`buildings`**: Vincula objetos no mundo a seus donos.
    *   `object_id`: ID do objeto (baú, fornalha, etc).
    *   `owner_id`: ID do Personagem ou Clã que é dono do objeto.
*   **`actor_position`**: Localização e classe dos objetos.
    *   `id`: ID do objeto.
    *   `class`: O caminho da classe Blueprint do Unreal Engine (ex: `BP_PL_Chest_Large_C`).

---

## 2. Rastreamento de Itens (Lógica de Propriedade)

A propriedade de um item segue dois fluxos distintos dependendo do `inv_type`:

### A. Itens com o Jogador (`inv_type` 0, 1, 2, 6, 7)
O `owner_id` na tabela `item_inventory` aponta **diretamente** para o `id` na tabela `characters`.

### B. Itens em Recipientes (`inv_type` 4)
O fluxo é mais complexo:
1.  Busca-se o item em `item_inventory` onde `inv_type = 4`.
2.  O `owner_id` do item é o `object_id` do recipiente (baú, bancada).
3.  Para descobrir quem é o dono desse baú, cruza-se o `object_id` com a tabela `buildings`.
4.  A coluna `owner_id` da tabela `buildings` revelará o ID do Personagem ou do Clã.

---

## 3. Extração de Dados e Parsing de Itens

### Parsing de BLOB Binário (Robusto)
A lógica implementada nos scripts segue a estrutura de serialização do Unreal Engine para extrair quantidades de dentro do campo `data`:
1.  **Ancoragem por Template ID**: Busca-se o `TemplateID` (4 bytes) no BLOB.
2.  **Contagem de Propriedades**: Lê-se o inteiro subsequente que indica o número de propriedades.
3.  **Busca por Propriedade ID 1**: A propriedade com ID 1 representa a **Quantidade**.

### Segurança e Performance
Todos os scripts utilizam o modo **Read-Only** (`file:game.db?mode=ro`) para garantir que o banco de dados não seja travado enquanto o servidor estiver online, evitando lag para os jogadores.

---

## 4. Tipos de Inventário Identificados

| ID (`inv_type`) | Localização |
| :--- | :--- |
| 0 | Mochila (Backpack) |
| 1 | Equipamento/Armadura Vestida |
| 2 | Atalhos (Hotbar) |
| 4 | Recipientes (Baús, Bancadas, Fornalhas) |
| 6 | Conhecimentos (Feats/Recipes) - Interno |
| 7 | Atributos/Perks - Interno |
| 12/13/14 | Slots de Máquinas e Estações de Trabalho |

---

## 5. Ferramentas Disponíveis

### `backpack_viewer.py`
Lista o inventário completo de um jogador, separado por categorias (Equipamento, Hotbar e Mochila).
**Uso:**
```bash
python3 backpack_viewer.py [NomeDoJogador]
```

### `clan_auditor.py`
Realiza uma auditoria completa de um clã, somando todos os itens presentes nos inventários de todos os membros e em todos os baús/bancadas pertencentes ao clã.
**Uso:**
```bash
python3 clan_auditor.py "Nome do Clã"
```

### `item_auditor.py`
Rastreia a localização exata de cada unidade de um item específico (pelo Template ID) em todo o servidor.
**Uso:**
```bash
python3 item_auditor.py <template_id>
```
