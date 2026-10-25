SET @add_family_members_relationship_key = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_members ADD COLUMN relationship_key VARCHAR(255) AFTER name', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_members'
    AND COLUMN_NAME = 'relationship_key'
);
PREPARE add_family_members_relationship_key_stmt FROM @add_family_members_relationship_key;
EXECUTE add_family_members_relationship_key_stmt;
DEALLOCATE PREPARE add_family_members_relationship_key_stmt;

SET @add_family_invitations_relationship_key = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_invitations ADD COLUMN relationship_key VARCHAR(255) AFTER name', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_invitations'
    AND COLUMN_NAME = 'relationship_key'
);
PREPARE add_family_invitations_relationship_key_stmt FROM @add_family_invitations_relationship_key;
EXECUTE add_family_invitations_relationship_key_stmt;
DEALLOCATE PREPARE add_family_invitations_relationship_key_stmt;

UPDATE family_members fm
JOIN app_option_items item
  ON item.catalog_key = 'guardian_identity_label'
 AND item.enabled = 1
 AND (item.item_key = fm.name OR item.label = fm.name)
SET fm.relationship_key = item.item_key
WHERE fm.relationship_key IS NULL OR fm.relationship_key = '';

UPDATE family_invitations fi
JOIN app_option_items item
  ON item.catalog_key = 'guardian_identity_label'
 AND item.enabled = 1
 AND (item.item_key = fi.name OR item.label = fi.name)
SET fi.relationship_key = item.item_key
WHERE fi.relationship_key IS NULL OR fi.relationship_key = '';
