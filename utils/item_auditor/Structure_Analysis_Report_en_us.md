# Structure Analysis Report: Conan Exiles `game.db`

This document details findings about the SQLite database structure of `game.db`, specifically regarding item tracking, inventories, ownership, and identification of named objects.

## 1. Main Tables

The structure uses a system of unique IDs to link objects across different tables:

*   **`characters`**: Contains player data.
    *   `id`: Unique numeric ID of the character.
    *   `char_name`: Visible name of the character.
    *   `guild`: ID of the guild (clan) to which the player belongs.
*   **`guilds`**: Contains clan data.
    *   `guildId`: Unique numeric ID of the clan.
    *   `name`: Name of the clan.
*   **`item_inventory`**: The central items table.
    *   `template_id`: The item ID (e.g., 11066 for Gold Coins).
    *   `owner_id`: The owner's ID (can be a Character or an Object/Chest).
    *   `inv_type`: Defines the inventory category.
    *   `data`: A binary BLOB containing quantity and metadata.
*   **`buildings`**: Links objects in the world to their owners.
    *   `object_id`: ID of the object (chest, furnace, etc.).
    *   `owner_id`: ID of the Character or Clan that owns the object.
*   **`actor_position`**: Location and class of objects.
    *   `id`: ID of the object.
    *   `class`: The Blueprint class path (e.g., `/Game/.../BP_PL_Chest_Large_C`).
*   **`properties`**: Stores metadata and custom names of objects.
    *   `object_id`: ID of the linked object.
    *   `name`: Name of the technical property (e.g., `BP_PL_Chest_Large_C.m_BuildableName`).
    *   `value`: BLOB containing the property value (often strings in binary format).

---

## 2. Item Tracking (Ownership Logic)

Item ownership follows two distinct flows depending on `inv_type`:

### A. Items with the Player (`inv_type` 0, 1, 2, 6, 7)
The `owner_id` in the `item_inventory` table points **directly** to the `id` in the `characters` table.

### B. Items in Containers (`inv_type` 4)
The flow is more complex:
1.  Look for the item in `item_inventory` where `inv_type = 4`.
2.  The `owner_id` of the item is the `object_id` of the container (chest, workbench).
3.  To find who owns this chest, cross-reference the `object_id` with the `buildings` table.
4.  The `owner_id` column of the `buildings` table will reveal the Character or Clan ID.

---

## 3. Identifying Objects by Custom Name

To identify specific chests or stations named by players (e.g., "Trading" chest):
1.  **Name Property**: The game uses the `m_BuildableName` property preceded by the object's class name.
2.  **Binary Search**: Since the name is stored in a BLOB, the search must be done via Hexadecimal comparison.
    *   Example: To find "Trading" (`54726164696E67`), use `WHERE hex(value) LIKE '%54726164696E67%'`.
3.  **Unique Location**: Identifying the `object_id` through this table allows the bot to monitor only that specific inventory, regardless of where it is moved on the map.

---

## 4. Data Extraction and Item Parsing (BLOB)

The structure of the `data` field (BLOB) follows a block serialization pattern. To extract information, the algorithm must traverse the binary identifying anchors and counters.

### BLOB Structure
1.  **Header (16 bytes)**: Contains magic identifiers like `0xEFBEADDE` (`DEADBEEF`).
2.  **Initial Strings**: Blueprint class path and instance name (format: `[4 bytes Length][N bytes ASCII String]`).
3.  **Template Block**:
    *   **Anchor (4 bytes)**: The item's `TemplateID` (e.g., `10097` in Little Endian).
    *   **Counter (4 bytes)**: Number of properties in this block.
    *   **Property Pairs**: Sequences of `[ID (4 bytes)][Value (4 bytes)]`.
4.  **Secondary Blocks**: Frequently started directly by a **Counter** (4 bytes), followed by `[ID][Value]` pairs.

### Confirmed Technical Mapping

| ID | Type | Description | Observation |
| :--- | :--- | :--- | :--- |
| **1** | Integer | **Quantity** | Present only in stackable items. |
| **6** | Integer | **Light Damage** | Includes kit and crafter bonuses. |
| **7** | Integer | **Heavy Damage** | Includes kit and crafter bonuses. |
| **34** | Integer | **Concussive Damage L.** | Stun damage (light hit). |
| **35** | Integer | **Concussive Damage H.** | Stun damage (heavy hit). |
| **14** | Integer | **Harvest Damage** | Collection damage for tools. |
| **40** | Integer | **Active Ammo/Applied Kit** | Template ID of the applied ammo/kit (e.g., 92191 - Bulked Plating). |
| **54** | Integer | **Crafter ID Low** | Unique creator ID (bonus link). |
| **55** | Integer | **Crafter ID High** | High part of the creator ID. |
| **63** | Integer | **Kit Bonus / Mod Flag** | Activates pink background and blocks new attachments. |
| **66** | Integer | **Crafter Tier** | Crafter level (e.g., 4 for T4). |
| **67** | Integer | **Crafter Profession** | Crafter profession. |
| **4** | Float | **Armor Value** | Total Armor Rating of the piece. |
| **5** | Float | **Weight** | Current weight (can be reduced by crafters/kits). |
| **7** | Float | **Max Durability** | Set by crafters or kits (e.g., 880.87). |
| **8** | Float | **Current Durability** | Represents the item's remaining HP. |
| **11** | Float | **Total Penetration** | Final percentage value (e.g., 0.5925 = 59.25%). |
| **29** | Float | **Bonus Multiplier 1** | Attribute multiplier (ID in 71). |
| **30** | Float | **Bonus Multiplier 2** | Attribute multiplier (ID in 72). |
| **71** | Integer | **Bonus Stat ID 1** | ID of the buffed attribute (e.g., 17, 19). |
| **72** | Integer | **Bonus Stat ID 2** | ID of the second buffed attribute. |

### "Write by Exception" Logic
The Conan Exiles database optimizes space by omitting properties that have the default value of the `TemplateID`.
*   **New Items**: Properties like Durability (ID 8) and Damage (ID 6/7) are not in the BLOB until the item suffers wear or modification.
*   **Kits**: When applying a kit, the game inserts the modifier ID (**ID 40**) and the bonus value (**ID 63**), in addition to updating the final attribute (ID 4 for armor or ID 11 for penetration).
*   **Passive Wear**: Some items (e.g., special bows) have temporal durability consumption. In these cases, small differences in ID 8 between original and copy are expected due to the time elapsed between spawn and database reading.

### Modification RCON Commands (Real Time)
Item manipulation with the server online is possible via console commands (`con {idx}`), avoiding the need to restart the server to inject custom items:

*   **`SetInventoryItemIntStat <slot> <prop_id> <value> <inv_type>`**:
    *   Used for Integers (IDs 1, 6, 7, 34, 35, 40, 54, 55, 63, 66, 67, 71, 72).
    *   Ex: `con 0 SetInventoryItemIntStat 1 63 12 2` (Applies kit flag on slot 1 of the hotbar).
*   **`SetInventoryItemFloatStat <slot> <prop_id> <value> <inv_type>`**:
    *   Used for Floats (IDs 4, 5, 7, 8, 11, 29, 30).
    *   Ex: `con 0 SetInventoryItemFloatStat 1 11 0.3540 2`.

---

## 5. Universal Duplication Logic
To ensure 100% fidelity (including mod items), duplication follows a dynamic approach:
1.  **Dynamic Extraction**: The bot traverses the BLOB's binary blocks and maps all `[ID: Value]` pairs, without relying on a fixed list.
2.  **Instance Filter**: The only ignored ID is **ID 22 (Instance ID)**, to avoid identity conflicts in the game engine.
3.  **Spawn and Injection**: A new base item is spawned via RCON and, after database synchronization (~5s), all captured properties are injected via `SetInventoryItem...Stat` commands.
4.  **Bonus Recalculation**: When restoring Crafter IDs (54/55) or Tier/Profession (66/67), the game automatically recalculates thrall bonuses after the player relogs.

### Attribute ID Table (for use with 71/72)
*   **14**: Vitality
*   **15**: Grit
*   **16**: Expertise
*   **17**: Strength (Might)
*   **19**: Agility (Athleticism)
*   **27**: Authority

---

## 8. Available Tools

### `backpack_viewer.py`
Lists a player's complete inventory.
### `clan_auditor.py`
Complete audit of all a clan's assets.
### `item_auditor.py` / `consultar_item.py`
Tracks a specific item across the server, grouping by owner.
