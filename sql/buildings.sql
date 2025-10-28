SELECT
    b.owner_id,
    COUNT(bi.instance_id) AS BuildPieces
FROM
    building_instances bi
JOIN
    buildings b ON bi.object_id = b.object_id
WHERE b.owner_id != 0
GROUP BY
    b.owner_id
ORDER BY
    BuildPieces DESC;