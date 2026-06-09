SET @add_emergency_contact_relationship_key = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE emergency_contacts ADD COLUMN relationship_key VARCHAR(255) AFTER relationship', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'emergency_contacts'
    AND COLUMN_NAME = 'relationship_key'
);
PREPARE add_emergency_contact_relationship_key_stmt FROM @add_emergency_contact_relationship_key;
EXECUTE add_emergency_contact_relationship_key_stmt;
DEALLOCATE PREPARE add_emergency_contact_relationship_key_stmt;

UPDATE emergency_contacts ec
LEFT JOIN app_option_items aoi
  ON aoi.catalog_key = 'guardian_identity_label'
  AND aoi.enabled = 1
  AND (aoi.item_key = ec.relationship OR aoi.label = ec.relationship)
SET ec.relationship_key = aoi.item_key,
    ec.relationship = COALESCE(aoi.label, ec.relationship)
WHERE (ec.relationship_key IS NULL OR ec.relationship_key = '')
  AND aoi.item_key IS NOT NULL;

UPDATE emergency_contacts ec
JOIN app_option_items aoi
  ON aoi.catalog_key = 'guardian_identity_label'
  AND aoi.item_key = CASE
    WHEN LOWER(ec.relationship) IN ('mother', 'mom') THEN 'mom'
    WHEN LOWER(ec.relationship) IN ('father', 'dad') THEN 'dad'
    WHEN LOWER(ec.relationship) IN ('guardian', 'caregiver', 'family', 'member', 'other', 'unknown', 'grandparent') THEN 'family_default'
    ELSE ''
  END
SET ec.relationship_key = aoi.item_key,
    ec.relationship = aoi.label
WHERE (ec.relationship_key IS NULL OR ec.relationship_key = '')
  AND ec.relationship IS NOT NULL
  AND ec.relationship <> '';
