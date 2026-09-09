-- learning_catalog_release_items uses variant_ordinal as its canonical
-- ordering column.  The full OpenMAIC runtime worker scans active release
-- items in that order, so keep the deployed schema aligned with the runtime
-- repository without adding a second, drift-prone ordinal column.
CREATE INDEX idx_learning_catalog_release_runtime_queue
  ON learning_catalog_release_items(
    release_id, status, quality_status, retired_at,
    variant_ordinal, course_id(96)
  );
