DO $$
DECLARE
    team_table regclass := to_regclass('teams');
    constraint_name text;
    unique_index record;
BEGIN
    IF team_table IS NULL THEN
        RAISE EXCEPTION 'teams table does not exist; apply migration 001 first';
    END IF;

    FOR constraint_name IN
        SELECT constraint_row.conname
        FROM pg_constraint AS constraint_row
        JOIN pg_attribute AS attribute_row
          ON attribute_row.attrelid = constraint_row.conrelid
         AND attribute_row.attnum = constraint_row.conkey[1]
        WHERE constraint_row.conrelid = team_table
          AND constraint_row.contype = 'u'
          AND array_length(constraint_row.conkey, 1) = 1
          AND attribute_row.attname = 'vehicle_id'
    LOOP
        EXECUTE format(
            'ALTER TABLE %s DROP CONSTRAINT %I',
            team_table,
            constraint_name
        );
    END LOOP;

    FOR unique_index IN
        SELECT namespace_row.nspname, index_row.relname
        FROM pg_index AS index_definition
        JOIN pg_class AS index_row
          ON index_row.oid = index_definition.indexrelid
        JOIN pg_namespace AS namespace_row
          ON namespace_row.oid = index_row.relnamespace
        JOIN pg_attribute AS attribute_row
          ON attribute_row.attrelid = index_definition.indrelid
         AND attribute_row.attnum = index_definition.indkey[0]
        WHERE index_definition.indrelid = team_table
          AND index_definition.indisunique
          AND NOT index_definition.indisprimary
          AND index_definition.indnkeyatts = 1
          AND attribute_row.attname = 'vehicle_id'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_constraint AS constraint_row
              WHERE constraint_row.conindid = index_definition.indexrelid
          )
    LOOP
        EXECUTE format(
            'DROP INDEX %I.%I',
            unique_index.nspname,
            unique_index.relname
        );
    END LOOP;
END;
$$;
