CREATE TABLE IF NOT EXISTS app_option_items (
  catalog_key VARCHAR(255) NOT NULL,
  item_key VARCHAR(255) NOT NULL,
  parent_key VARCHAR(255),
  label VARCHAR(255) NOT NULL,
  description VARCHAR(1024),
  image_asset VARCHAR(512),
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT NOT NULL DEFAULT 1,
  updated_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (catalog_key, item_key)
);

SET @add_app_option_items_parent_index = (
  SELECT IF(COUNT(*) = 0, 'CREATE INDEX idx_app_option_items_parent ON app_option_items(catalog_key, parent_key, sort_order)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'app_option_items'
    AND INDEX_NAME = 'idx_app_option_items_parent'
);
PREPARE add_app_option_items_parent_index_stmt FROM @add_app_option_items_parent_index;
EXECUTE add_app_option_items_parent_index_stmt;
DEALLOCATE PREPARE add_app_option_items_parent_index_stmt;

INSERT IGNORE INTO app_option_items(
  catalog_key, item_key, parent_key, label, description, image_asset, sort_order, enabled, updated_at
) VALUES
  ('guardian_identity_group', 'parent', NULL, '父母', '孩子的父亲或母亲。', NULL, 10, 1, 0),
  ('guardian_identity_group', 'grandparent', NULL, '祖辈', '孩子的爷爷奶奶或外公外婆。', NULL, 20, 1, 0),
  ('guardian_identity_group', 'family', NULL, '其他家人', '其他参与家庭看护的亲属或成员。', NULL, 30, 1, 0),

  ('guardian_identity_label', 'mom', 'parent', '妈妈', '母亲身份。', 'assets/images/guardian/guardian_mom.png', 10, 1, 0),
  ('guardian_identity_label', 'dad', 'parent', '爸爸', '父亲身份。', 'assets/images/guardian/guardian_dad.png', 20, 1, 0),

  ('guardian_identity_label', 'maternal_grandpa', 'grandparent', '外公', '母亲一侧祖辈。', 'assets/images/guardian/guardian_maternal_grandpa.png', 10, 1, 0),
  ('guardian_identity_label', 'maternal_grandma', 'grandparent', '外婆', '母亲一侧祖辈。', 'assets/images/guardian/guardian_maternal_grandma.png', 20, 1, 0),
  ('guardian_identity_label', 'grandpa', 'grandparent', '爷爷', '父亲一侧祖辈。', 'assets/images/guardian/guardian_grandpa.png', 30, 1, 0),
  ('guardian_identity_label', 'grandma', 'grandparent', '奶奶', '父亲一侧祖辈。', 'assets/images/guardian/guardian_grandma.png', 40, 1, 0),

  ('guardian_identity_label', 'aunt', 'family', '阿姨', '其他女性家庭成员。', 'assets/images/guardian/guardian_aunt.png', 10, 1, 0),
  ('guardian_identity_label', 'uncle', 'family', '叔叔', '其他男性家庭成员。', 'assets/images/guardian/guardian_uncle.png', 20, 1, 0),
  ('guardian_identity_label', 'paternal_aunt', 'family', '姑姑', '其他女性家庭成员。', 'assets/images/guardian/guardian_paternal_aunt.png', 30, 1, 0),
  ('guardian_identity_label', 'maternal_uncle', 'family', '舅舅', '其他男性家庭成员。', 'assets/images/guardian/guardian_maternal_uncle.png', 40, 1, 0),
  ('guardian_identity_label', 'family_default', 'family', '其他家人', '无法明确性别或年龄段的家庭成员。', 'assets/images/guardian/guardian_default.png', 50, 1, 0),

  ('family_role', 'admin', NULL, '管理员', '可管理成员、设备和全部设置。', NULL, 10, 1, 0),
  ('family_role', 'guardian', NULL, '监护人', '可查看看护状态并处理任务确认。', NULL, 20, 1, 0),
  ('family_role', 'viewer', NULL, '临时查看者', '可接收必要提醒，不管理设置。', NULL, 30, 1, 0);
