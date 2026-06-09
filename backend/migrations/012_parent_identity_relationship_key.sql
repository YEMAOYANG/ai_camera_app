SET @add_parent_identity_relationship_key = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE parent_identities ADD COLUMN relationship_key VARCHAR(255) AFTER relationship', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'parent_identities'
    AND COLUMN_NAME = 'relationship_key'
);
PREPARE add_parent_identity_relationship_key_stmt FROM @add_parent_identity_relationship_key;
EXECUTE add_parent_identity_relationship_key_stmt;
DEALLOCATE PREPARE add_parent_identity_relationship_key_stmt;

UPDATE parent_identities pi
LEFT JOIN app_option_items aoi
  ON aoi.catalog_key = 'guardian_identity_label'
  AND aoi.enabled = 1
  AND (aoi.item_key = pi.relationship OR aoi.label = pi.relationship)
SET pi.relationship_key = aoi.item_key,
    pi.relationship = COALESCE(aoi.label, pi.relationship)
WHERE (pi.relationship_key IS NULL OR pi.relationship_key = '')
  AND aoi.item_key IS NOT NULL;
