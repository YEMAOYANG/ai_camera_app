UPDATE app_option_items
SET description = '可管理成员、设备和全部家庭设置。',
    metadata_json = '{"capabilities":["manage_family_members","manage_family_code","manage_devices","manage_privacy","manage_subscription","manage_child_profile","manage_child_settings","manage_emergency_contacts","manage_rewards","manage_tasks","confirm_tasks","view_live_care","view_reports","view_points_rewards","manage_account_security"]}'
WHERE catalog_key = 'family_role' AND item_key = 'admin';

UPDATE app_option_items
SET description = '可维护孩子资料、任务、奖励和紧急联系人，不管理成员和设备。',
    metadata_json = '{"capabilities":["manage_child_profile","manage_child_settings","manage_emergency_contacts","manage_rewards","manage_tasks","confirm_tasks","view_live_care","view_reports","view_points_rewards","manage_account_security"]}'
WHERE catalog_key = 'family_role' AND item_key = 'guardian';

UPDATE app_option_items
SET description = '可接收必要提醒和查看基础状态，不管理设置。',
    metadata_json = '{"capabilities":["view_basic_home","view_alerts","manage_account_security"]}'
WHERE catalog_key = 'family_role' AND item_key = 'viewer';
