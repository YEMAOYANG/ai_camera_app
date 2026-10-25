-- MySQL-compatible helpers (JSON functions, CAST AS UNSIGNED, GREATEST/LEAST) used
-- by backend SQL that predates PostgreSQL.
-- Paths use MySQL syntax ($, $.key, $."quoted key", $[0]); semantics follow
-- MySQL: JSON_UNQUOTE returns a string's value and any other JSON as text,
-- JSON_LENGTH counts object keys too, JSON_TYPE returns MySQL type names.
-- Text arguments are parsed as JSON, as MySQL does for string arguments.

CREATE FUNCTION mysql_json_path(path text) RETURNS text[] LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE
    WHEN path = '$' THEN ARRAY[]::text[]
    WHEN left(path, 1) <> '$' THEN NULL
    ELSE ARRAY(
      SELECT coalesce(m[1], m[2], m[3])
      FROM regexp_matches(substr(path, 2), '\.(?:"([^"]+)"|([A-Za-z0-9_$]+))|\[([0-9]+)\]', 'g')
        WITH ORDINALITY AS part(m, ordinal)
      ORDER BY ordinal)
  END
$$;

CREATE FUNCTION json_extract(doc jsonb, path text) RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT doc #> mysql_json_path(path)
$$;
CREATE FUNCTION json_extract(doc text, path text) RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT doc::jsonb #> mysql_json_path(path)
$$;

CREATE FUNCTION json_unquote(value jsonb) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE WHEN jsonb_typeof(value) = 'string' THEN value #>> '{}' ELSE value::text END
$$;
CREATE FUNCTION json_unquote(value text) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE
    WHEN pg_input_is_valid(value, 'jsonb') AND jsonb_typeof(value::jsonb) = 'string' THEN value::jsonb #>> '{}'
    ELSE value
  END
$$;

CREATE FUNCTION json_valid(value text) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT pg_input_is_valid(value, 'jsonb')
$$;
CREATE FUNCTION json_valid(value jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT true
$$;

CREATE FUNCTION json_type(value jsonb) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_type(value)
$$;
CREATE FUNCTION json_type(value text) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_type(value::jsonb)
$$;

CREATE FUNCTION json_length(value jsonb) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_length(value)
$$;
CREATE FUNCTION json_length(value text) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_length(value::jsonb)
$$;
CREATE FUNCTION json_length(doc jsonb, path text) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_length(json_extract(doc, path))
$$;
CREATE FUNCTION json_length(doc text, path text) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_length(json_extract(doc, path))
$$;

-- JSON_CONTAINS follows MySQL: a non-array candidate is contained in an array
-- when some element contains it, at any depth. PostgreSQL's @> also needs the
-- same structure there, so it serves only as the fast path: when @> holds,
-- MySQL's rule holds too.
CREATE FUNCTION mysql_json_contains(target jsonb, candidate jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
  item jsonb;
  member text;
BEGIN
  IF target @> candidate THEN
    RETURN true;
  END IF;
  CASE jsonb_typeof(target)
    WHEN 'array' THEN
      IF jsonb_typeof(candidate) = 'array' THEN
        FOR item IN SELECT element.value FROM jsonb_array_elements(candidate) AS element LOOP
          IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(target) AS element
                         WHERE mysql_json_contains(element.value, item)) THEN
            RETURN false;
          END IF;
        END LOOP;
        RETURN true;
      END IF;
      RETURN EXISTS (SELECT 1 FROM jsonb_array_elements(target) AS element
                     WHERE mysql_json_contains(element.value, candidate));
    WHEN 'object' THEN
      IF jsonb_typeof(candidate) <> 'object' THEN
        RETURN false;
      END IF;
      FOR member IN SELECT jsonb_object_keys(candidate) LOOP
        IF NOT (target ? member AND mysql_json_contains(target -> member, candidate -> member)) THEN
          RETURN false;
        END IF;
      END LOOP;
      RETURN true;
    ELSE
      RETURN false;
  END CASE;
END
$$;

CREATE FUNCTION json_contains(target jsonb, candidate jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(target, candidate)
$$;
CREATE FUNCTION json_contains(target text, candidate text) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(target::jsonb, candidate::jsonb)
$$;

CREATE FUNCTION json_remove(doc jsonb, path text) RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT doc #- mysql_json_path(path)
$$;
CREATE FUNCTION json_remove(doc text, path text) RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT doc::jsonb #- mysql_json_path(path)
$$;

-- CAST(text AS UNSIGNED) as MySQL evaluates it: the leading digits, or 0 when
-- there are none, instead of an error that would fail the whole query.
CREATE FUNCTION mysql_unsigned(value text) RETURNS bigint LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE
    WHEN value ~ '^\s*\+?[0-9]' THEN least(substring(value FROM '^\s*\+?([0-9]+)')::numeric, 9223372036854775807)::bigint
    ELSE 0
  END
$$;

-- JSON_CONTAINS(target, candidate[, path]) with mixed text/jsonb arguments.
CREATE FUNCTION json_contains(target text, candidate jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(target::jsonb, candidate)
$$;
CREATE FUNCTION json_contains(target jsonb, candidate text) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(target, candidate::jsonb)
$$;
-- A missing path gives NULL, as in MySQL.
CREATE FUNCTION json_contains(target jsonb, candidate jsonb, path text) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(json_extract(target, path), candidate)
$$;
CREATE FUNCTION json_contains(target text, candidate jsonb, path text) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(json_extract(target, path), candidate)
$$;
CREATE FUNCTION json_contains(target text, candidate text, path text) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT mysql_json_contains(json_extract(target, path), candidate::jsonb)
$$;

-- MySQL GREATEST/LEAST return NULL when any argument is NULL; PostgreSQL's
-- ignore NULLs. STRICT gives the MySQL result.
CREATE FUNCTION mysql_least(a bigint, b bigint) RETURNS bigint LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT least(a, b)
$$;
CREATE FUNCTION mysql_greatest(a bigint, b bigint) RETURNS bigint LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT greatest(a, b)
$$;
