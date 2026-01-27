drop table if exists GoldCoinCounter;
create table GoldCoinCounter (item_id bigint, owner_id bigint, inv_type bigint, template_id bigint, data blob, realOwnerId bigint, realOwnerName text, class text, finderNibble bigint, goldValueHex text, goldValueInt bigint);

insert into GoldCoinCounter (item_id, owner_id, inv_type, template_id, data) select i.item_id, i.owner_id, i.inv_type, i.template_id, i.data from item_inventory as i where i.template_id = 11066 and ( i.inv_type = 4 or i.inv_type = 0 );
update GoldCoinCounter as gcc set realOwnerId = ( 
    select coalesce(
    ( select id from characters as c where c.id = gcc.owner_id and gcc.inv_type = 0),
    ( select guildId from guilds as g where g.guildId = gcc.owner_id and gcc.inv_type = 0),
--    ( select ownerId from ListOfThralls as l where l.id = gcc.owner_id and gcc.inv_type = 0),
-- uncomment only if you have the ListOfThralls table populated. If you do not, thrall inventories are excluded.
    ( select b.owner_id from buildings as b where b.object_id = gcc.owner_id and inv_type = 4) ) );
update GoldCoinCounter as gcc set realOwnerName = (
    select coalesce(
    ( select char_name from characters as c where c.id = gcc.realOwnerId ),
    ( select name from guilds as g where g.guildId = gcc.realOwnerId) ) );
update GoldCoinCounter as gcc set class = ( select class from actor_position as a where a.id = gcc.owner_id );
update GoldCoinCounter as gcc set finderNibble = instr(hex(gcc.data),'001600') - 6;
update GoldCoinCounter as gcc set goldValueHex = ( substr(hex(gcc.data),gcc.finderNibble+2,2) || substr(hex(gcc.data),gcc.finderNibble,2) );
update GoldCoinCounter as gcc set goldValueInt = (
 WITH RECURSIVE
            unhex(str, val, weight) AS (
                select gcc.goldValueHex, 0, 1
                UNION ALL
                SELECT 
                  substr(str, 1, length(str) - 1),
                  val + (instr('0123456789ABCDEF', substr(str, length(str), 1)) - 1) * weight,
                  weight * 16
                FROM unhex WHERE length(str) > 0
                )
            SELECT val FROM unhex order by weight desc limit 1
            );
 
select realOwnerId as 'Owner ID', realOwnerName as 'Owner Name', sum(goldValueInt) as 'Gold Coins' from GoldCoinCounter group by realOwnerId order by sum(goldValueInt) desc;

--drop table GoldCoinCounter;
--this table is probably fine to leave in your database, but uncomment this if you want to delete it at the end.
