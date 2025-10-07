SELECT
    COALESCE(g.name, c.char_name, 'Unknown') AS Owner,
    COUNT(bi.instance_id) AS BuildPieces
FROM
    building_instances bi
JOIN
    buildings b ON bi.object_id = b.object_id
LEFT JOIN
    characters c ON b.owner_id = c.id
LEFT JOIN
    guilds g ON b.owner_id = g.guildId
WHERE b.owner_id != 0
GROUP BY
    b.owner_id
ORDER BY
    BuildPieces DESC;