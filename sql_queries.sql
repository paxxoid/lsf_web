/* will provide the total raid minutes for all raids in the last 90 days */

SELECT
    SUM(max_raid_minutes) AS total_raid_minutes FROM (
SELECT
    a.raid_event_id,
    b.start_at,
    MAX(a.total_raid_minutes) AS max_raid_minutes
FROM guild_raidattendance a
LEFT JOIN guild_raidevent b
    ON a.raid_event_id = b.id
WHERE b.start_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
GROUP BY
    a.raid_event_id,
    b.start_at
ORDER BY b.start_at
) AS raids;






/* scribbles */
SELECT * from  guild_raidattendance;

SELECT
    a.raid_event_id,
    b.start_at,
    MAX(a.total_raid_minutes) AS max_raid_minutes
FROM guild_raidattendance a
LEFT JOIN guild_raidevent b
    ON a.raid_event_id = b.id
GROUP BY
    a.raid_event_id,
    b.start_at;