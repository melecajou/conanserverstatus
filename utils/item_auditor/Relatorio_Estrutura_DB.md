# Relatório de Análise de Estrutura: Conan Exiles `game.db`

Este documento detalha as descobertas sobre a estrutura do banco de dados SQLite `game.db`, especificamente no que tange ao rastreamento de itens, inventários, propriedade e identificação de objetos nomeados.

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
    *   `class`: O caminho da classe Blueprint (ex: `/Game/.../BP_PL_Chest_Large_C`).
*   **`properties`**: Armazena metadados e nomes personalizados de objetos.
    *   `object_id`: ID do objeto vinculado.
    *   `name`: Nome da propriedade técnica (ex: `BP_PL_Chest_Large_C.m_BuildableName`).
    *   `value`: BLOB contendo o valor da propriedade (frequentemente strings em formato binário).

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

## 3. Identificação de Objetos por Nome Customizado

Para identificar baús ou estações específicas que foram nomeadas pelos jogadores (ex: baú "Trading"):
1.  **Propriedade de Nome**: O jogo utiliza a propriedade `m_BuildableName` precedida pelo nome da classe do objeto.
2.  **Busca Binária**: Como o nome é armazenado em um BLOB, a busca deve ser feita via comparação Hexadecimal.
    *   Exemplo: Para encontrar "Trading" (`54726164696E67`), usa-se `WHERE hex(value) LIKE '%54726164696E67%'`.
3.  **Localização Única**: Identificar o `object_id` através desta tabela permite que o bot monitore apenas aquele inventário específico, independentemente de onde ele seja movido no mapa.

---

## 4. Extração de Dados e Parsing de Itens (BLOB)

A estrutura do campo `data` (BLOB) segue um padrão de serialização por blocos. Para extrair informações, o algoritmo deve percorrer o binário identificando âncoras e contadores.

### Estrutura do BLOB
1.  **Header (16 bytes)**: Contém identificadores mágicos como `0xEFBEADDE` (`DEADBEEF`).
2.  **Strings Iniciais**: Caminho da classe Blueprint e nome da instância (formato: `[4 bytes Comprimento][N bytes String ASCII]`).
3.  **Bloco de Template**:
    *   **Âncora (4 bytes)**: O `TemplateID` do item (ex: `10097` em Little Endian).
    *   **Contador (4 bytes)**: Número de propriedades neste bloco.
    *   **Pares de Propriedades**: Sequências de `[ID (4 bytes)][Valor (4 bytes)]`.
4.  **Blocos Secundários**: Frequentemente iniciados diretamente por um **Contador** (4 bytes), seguidos pelos pares `[ID][Valor]`.

### Mapeamento Técnico Confirmado

| ID | Tipo | Descrição | Observação |
| :--- | :--- | :--- | :--- |
| **1** | Integer | **Quantidade** | Presente apenas em itens empilháveis (Stackable). |
| **6** | Integer | **Dano Leve** | Inclui bônus de kits e artesãos. |
| **7** | Integer | **Dano Pesado** | Inclui bônus de kits e artesãos. |
| **34** | Integer | **Dano Concussivo L.** | Dano de atordoamento (golpe leve). |
| **35** | Integer | **Dano Concussivo P.** | Dano de atordoamento (golpe pesado). |
| **14** | Integer | **Harvest Damage** | Dano de coleta para ferramentas. |
| **40** | Integer | **Munição Ativa/Kit Aplicao** | Template ID da munição/kit aplicado (ex: 92191 - Bulked Plating). |
| **54** | Integer | **Crafter ID Low** | ID único do criador (vínculo de bônus). |
| **55** | Integer | **Crafter ID High** | Parte alta do ID do criador. |
| **63** | Integer | **Bônus de Kit / Flag Mod** | Ativa o fundo rosa e bloqueia novos apetrechos. |
| **66** | Integer | **Crafter Tier** | Nível do artesão (Ex: 4 para T4). |
| **67** | Integer | **Crafter Profession** | Profissão do artesão. |
| **4** | Float | **Valor de Armadura** | Armor Rating total da peça. |
| **5** | Float | **Peso** | Peso atual (pode ser reduzido por artesãos/kits). |
| **7** | Float | **Durabilidade Máxima** | Definida por artesãos ou kits (ex: 880.87). |
| **8** | Float | **Durabilidade Atual** | Representa o HP restante do item. |
| **11** | Float | **Penetração Total** | Valor percentual final (ex: 0.5925 = 59.25%). |
| **29** | Float | **Bonus Multiplier 1** | Multiplicador de atributo (ID em 71). |
| **30** | Float | **Bonus Multiplier 2** | Multiplicador de atributo (ID em 72). |
| **71** | Integer | **Bonus Stat ID 1** | ID do atributo bonificado (ex: 17, 19). |
| **72** | Integer | **Bonus Stat ID 2** | ID do segundo atributo bonificado. |

### Lógica de "Gravação por Exceção"
O banco de dados do Conan Exiles otimiza o espaço omitindo propriedades que possuam o valor padrão do `TemplateID`.
*   **Itens Novos**: Propriedades como Durabilidade (ID 8) e Dano (ID 6/7) não constam no BLOB até que o item sofra desgaste ou modificação.
*   **Kits**: Ao aplicar um kit, o jogo insere o ID do modificador (**ID 40**) e o valor do bônus (**ID 63**), além de atualizar o atributo final (ID 4 para armadura ou ID 11 para penetração).
*   **Desgaste Passivo**: Alguns itens (ex: arcos especiais) possuem consumo de durabilidade temporal. Nestes casos, pequenas diferenças no ID 8 entre original e cópia são esperadas devido ao tempo decorrido entre o spawn e a leitura do banco.

### Comandos RCON de Modificação (Tempo Real)
A manipulação de itens com o servidor online é possível via comandos de console (`con {idx}`), evitando a necessidade de reiniciar o servidor para injetar itens customizados:

*   **`SetInventoryItemIntStat <slot> <prop_id> <valor> <inv_type>`**:
    *   Usado para Integers (IDs 1, 6, 7, 34, 35, 40, 54, 55, 63, 66, 67, 71, 72).
    *   Ex: `con 0 SetInventoryItemIntStat 1 63 12 2` (Aplica flag de kit no slot 1 da hotbar).
*   **`SetInventoryItemFloatStat <slot> <prop_id> <valor> <inv_type>`**:
    *   Usado para Floats (IDs 4, 5, 7, 8, 11, 29, 30).
    *   Ex: `con 0 SetInventoryItemFloatStat 1 11 0.3540 2`.

---

## 5. Lógica de Duplicação Universal
Para garantir 100% de fidelidade (incluindo itens de mods), a duplicação segue uma abordagem dinâmica:
1.  **Extração Dinâmica**: O bot percorre os blocos binários do BLOB e mapeia todos os pares `[ID: Valor]`, sem depender de uma lista fixa.
2.  **Filtro de Instância**: O único ID ignorado é o **ID 22 (Instance ID)**, para evitar conflitos de identidade no motor do jogo.
3.  **Spawn e Injeção**: Um novo item base é spawnado via RCON e, após sincronização do banco (~5s), todas as propriedades capturadas são injetadas via comandos `SetInventoryItem...Stat`.
4.  **Recálculo de Bônus**: Ao restaurar os IDs de Crafter (54/55) ou Tier/Profession (66/67), o jogo recalcula os bônus de lacaio automaticamente após o relog do jogador.

### Tabela de IDs de Atributos (para usar com 71/72)
*   **14**: Vitality
*   **15**: Grit
*   **16**: Expertise
*   **17**: Strength (Might)
*   **19**: Agility (Athleticism)
*   **27**: Authority

---

## 8. Ferramentas Disponíveis

### `backpack_viewer.py`
Lista o inventário completo de um jogador.
### `clan_auditor.py`
Auditoria completa de todos os bens de um clã.
### `item_auditor.py` / `consultar_item.py`
Rastreia um item específico em todo o servidor, agrupando por proprietário.
