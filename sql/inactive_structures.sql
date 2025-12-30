WITH GuildActivity AS (
    SELECT guild as guildId, MAX(lastTimeOnline) as lastGuildActivity
    FROM characters
    WHERE guild IS NOT NULL
    GROUP BY guild
),
BuildingOwnersWithActivity AS (
    SELECT b.owner_id, bi.instance_id, ap.x, ap.y, ap.z, c.char_name, g.name as guild_name, COALESCE(ga.lastGuildActivity, c.lastTimeOnline) as last_activity_timestamp
    FROM building_instances AS bi
    JOIN buildings b ON b.object_id = bi.object_id
    JOIN actor_position ap ON ap.id = bi.object_id
    LEFT JOIN characters c ON b.owner_id = c.id
    LEFT JOIN guilds g ON b.owner_id = g.guildId
    LEFT JOIN GuildActivity ga ON b.owner_id = ga.guildId
)
SELECT COALESCE(guild_name, char_name) AS Owner, COUNT(instance_id) AS Pieces, 'TeleportPlayer ' || x || ' ' || y || ' ' || z AS Location, DATETIME(last_activity_timestamp, 'unixepoch', '-3 hours') AS LastActivity_GMT3
FROM BuildingOwnersWithActivity
WHERE last_activity_timestamp < CAST(strftime('%s', 'now', '-' || ? || ' days') AS INT) AND Owner IS NOT NULL
GROUP BY Owner, x, y, z
ORDER BY LOWER(Owner), Pieces DESC;
