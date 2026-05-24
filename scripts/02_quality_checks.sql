-- Andmekvaliteedi kontrollid: käivitab quality.run_checks() (täielik loogika on init/07_quality_objects.sql).
-- Kasutus käsurealt:
--   docker compose exec db psql -U praktikum -d praktikum -f /app/scripts/02_quality_checks.sql
-- (pipeline konteineris on tee tavaliselt `/app/scripts/...`.)

SELECT quality.run_checks('manual_psql');
