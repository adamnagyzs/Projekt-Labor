-- 1. Mely beolvasott kódokhoz nem tartozik eszköz?
-- Az ismeretlen kódokat kódonként csoportosítjuk, és megmutatjuk,
-- hányszor került elő ugyanaz az ismeretlen címke az aktív időszakban.

SELECT
    scan.raw_code AS ismeretlen_kod,
    COUNT(*) AS beolvasasok_szama
FROM scan
JOIN inventory_session
    ON inventory_session.id = scan.session_id
JOIN inventory_period
    ON inventory_period.id = inventory_session.period_id
WHERE scan.result = 'UNKNOWN_CODE'
  AND inventory_period.state = 'ACTIVE'
GROUP BY scan.raw_code
ORDER BY beolvasasok_szama DESC, ismeretlen_kod;


-- 2. Mely eszközök kerültek elő idegen körzetből?
-- A munkamenet körzete és az eszköz saját körzete eltér; ezeket
-- FOREIGN_ZONE eredményű scan eseményekből állítjuk elő.

SELECT
    scan.raw_code AS beolvasott_kod,
    asset.asset_number AS eszkozszam,
    asset.sub_number AS alszam,
    asset.name AS eszkoz_neve,
    own_zone.code AS eszkoz_sajat_korzete,
    session_zone.code AS beolvasas_korzete,
    scan.scanned_at AS beolvasas_ideje
FROM scan
JOIN inventory_session
    ON inventory_session.id = scan.session_id
JOIN inventory_period
    ON inventory_period.id = inventory_session.period_id
JOIN asset
    ON asset.id = scan.asset_id
JOIN inventory_zone AS own_zone
    ON own_zone.id = asset.zone_id
JOIN inventory_zone AS session_zone
    ON session_zone.id = inventory_session.zone_id
WHERE scan.result = 'FOREIGN_ZONE'
  AND inventory_period.state = 'ACTIVE'
ORDER BY scan.scanned_at;


-- 3. Mi hiányzik a 262-es körzetből?
-- A körzet minden eszközét összevetjük ugyanazon aktív időszak
-- 262-es munkameneteiben találtként rögzített eszközökkel.
-- A lekérdezés csak a hiányzó tételek darabszámát adja vissza.

SELECT
    COUNT(*) AS hianyzo_tetelek_szama
FROM asset
JOIN inventory_zone
    ON inventory_zone.id = asset.zone_id
WHERE inventory_zone.code = '262'
  AND NOT EXISTS (
      SELECT 1
      FROM scan
      JOIN inventory_session
          ON inventory_session.id = scan.session_id
      JOIN inventory_period
          ON inventory_period.id = inventory_session.period_id
      WHERE scan.asset_id = asset.id
        AND scan.result = 'FOUND'
        AND inventory_session.zone_id = asset.zone_id
        AND inventory_period.state = 'ACTIVE'
  );


-- 4. Tételenként mennyi a nyilvántartott és a beolvasott mennyiség?
-- Csak a ténylegesen beolvasott eszközöket mutatjuk. A megtalált és
-- az idegen körzetben előkerült eszközök beolvasási mennyisége is
-- szerepel, mert mindkettő fizikai előkerülést jelent.

SELECT
    asset.asset_number AS eszkozszam,
    asset.sub_number AS alszam,
    asset.name AS eszkoz_neve,
    own_zone.code AS eszkoz_sajat_korzete,
    asset.quantity AS nyilvantartott_mennyiseg,
    SUM(scan.quantity_delta) AS beolvasott_mennyiseg,
    asset.quantity - SUM(scan.quantity_delta) AS elteres
FROM scan
JOIN inventory_session
    ON inventory_session.id = scan.session_id
JOIN inventory_period
    ON inventory_period.id = inventory_session.period_id
JOIN asset
    ON asset.id = scan.asset_id
JOIN inventory_zone AS own_zone
    ON own_zone.id = asset.zone_id
WHERE scan.result IN ('FOUND', 'FOREIGN_ZONE')
  AND inventory_period.state = 'ACTIVE'
GROUP BY
    asset.id,
    asset.asset_number,
    asset.sub_number,
    asset.name,
    own_zone.code,
    asset.quantity
ORDER BY own_zone.code, asset.asset_number, asset.sub_number;

-- 5. Típusonként hány eszköztétel van, körzetenként?
-- Minden asset sor egy tétel, a tartozékok is beleszámítanak.
-- Az eszköz fizikai darabszámát nem összegezzük: ez COUNT, nem SUM(quantity).
-- A típus nélküli eszközöket külön csoportban jelenítjük meg.

SELECT
    inventory_zone.code AS korzet,
    asset_type.id AS tipus_id,
    COALESCE(asset_type.name, 'Nincs típus') AS tipus,
    COUNT(asset.id) AS tetelek_szama
FROM asset
JOIN inventory_zone
    ON inventory_zone.id = asset.zone_id
LEFT JOIN asset_type
    ON asset_type.id = asset.asset_type_id
GROUP BY
    inventory_zone.code,
    asset_type.id,
    asset_type.name
ORDER BY
    inventory_zone.code,
    tipus,
    asset_type.id;

-- 6. Felelősönként hány eszköz tartozik hozzá most, és hány volt valaha?
-- A felelős-kapcsolat időbélyeges: váltáskor a régi sor valid_to-t kap, nem törlődik.
-- A "most" a nyitott sorokat számolja, a "valaha" a lezártakat is.

SELECT
    person.name AS felelos,
    COUNT(asset_responsible.id) FILTER (WHERE asset_responsible.valid_to IS NULL) AS most,
    COUNT(asset_responsible.id) AS valaha
FROM person
LEFT JOIN asset_responsible
    ON asset_responsible.person_id = person.id
GROUP BY person.name
ORDER BY person.name;
