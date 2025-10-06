DROP VIEW IF EXISTS Structure_Locations;
    CREATE VIEW Structure_Locations AS 
    SELECT 
        COALESCE(g.name, c.char_name) AS Owner,  
        COUNT(bi.instance_id) AS Pieces, 
        'TeleportPlayer ' || ap.x || ' ' || ap.y || ' ' || ap.z AS Location 
    FROM building_instances AS bi 
    JOIN buildings b ON b.object_id = bi.object_id 
    JOIN actor_position ap ON ap.id = bi.object_id 
    LEFT JOIN guilds g ON b.owner_id = g.guildId 
    LEFT JOIN characters c ON b.owner_id = c.id 
    GROUP BY Owner, ap.x, ap.y, ap.z  
    ORDER BY LOWER(Owner), Pieces DESC;

SELECT 
    Owner AS ClanName, 
    SUM(Pieces) AS BuildPieces
FROM Structure_Locations
GROUP BY Owner
ORDER BY BuildPieces DESC;