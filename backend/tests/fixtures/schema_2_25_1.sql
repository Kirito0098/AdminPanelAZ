-- Схема БД чистой установки 2.25.1 (6dfda3f): create_all + run_db_migrations того релиза.
CREATE TABLE active_web_session (
	id INTEGER NOT NULL, 
	session_id VARCHAR(64) NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	remote_addr VARCHAR(64), 
	user_agent VARCHAR(255), 
	created_at DATETIME NOT NULL, 
	last_seen_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE alert_rules (
	id INTEGER NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	metric VARCHAR(29) NOT NULL, 
	operator VARCHAR(3) NOT NULL, 
	threshold FLOAT NOT NULL, 
	node_id INTEGER, 
	cooldown_minutes INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	last_triggered_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE amneziawg2_access_policies (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	client_name VARCHAR(64) NOT NULL, 
	access_until DATETIME, 
	is_temp_blocked BOOLEAN NOT NULL, 
	is_permanent_blocked BOOLEAN NOT NULL, 
	block_reason VARCHAR(32), 
	block_started_at DATETIME, 
	block_days INTEGER, 
	block_until DATETIME, 
	traffic_limit_bytes BIGINT, 
	traffic_limit_period_days INTEGER, 
	updated_by VARCHAR(64), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_awg2_access_node_client UNIQUE (node_id, client_name), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE antifilter_cidr (
	id INTEGER NOT NULL, 
	cidr VARCHAR(50) NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE antifilter_meta (
	id INTEGER NOT NULL, 
	cidr_count INTEGER NOT NULL, 
	last_refreshed_at DATETIME, 
	refresh_status VARCHAR(16) NOT NULL, 
	refresh_error TEXT, 
	PRIMARY KEY (id)
);
CREATE TABLE app_settings (
	id INTEGER NOT NULL, 
	"key" VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE background_task (
	id VARCHAR(32) NOT NULL, 
	task_type VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_by_username VARCHAR(80), 
	message VARCHAR(255), 
	output TEXT, 
	error TEXT, 
	progress_percent INTEGER NOT NULL, 
	progress_stage VARCHAR(255), 
	created_at DATETIME NOT NULL, 
	started_at DATETIME, 
	finished_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE cidr_db_refresh_log (
	id INTEGER NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	status VARCHAR(16) NOT NULL, 
	providers_updated INTEGER NOT NULL, 
	providers_failed INTEGER NOT NULL, 
	total_cidrs INTEGER NOT NULL, 
	error VARCHAR(512), 
	triggered_by VARCHAR(64), 
	details_json TEXT, 
	PRIMARY KEY (id)
);
CREATE TABLE client_portal_tokens (
	id INTEGER NOT NULL, 
	token VARCHAR(64) NOT NULL, 
	node_id INTEGER NOT NULL, 
	client_name VARCHAR(32) NOT NULL, 
	created_by_user_id INTEGER, 
	created_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_client_portal_token UNIQUE (token), 
	FOREIGN KEY(node_id) REFERENCES nodes (id), 
	FOREIGN KEY(created_by_user_id) REFERENCES users (id)
);
CREATE TABLE client_templates (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	vpn_type VARCHAR(10) NOT NULL, 
	cert_expire_days INTEGER, 
	traffic_limit_value FLOAT, 
	traffic_limit_unit VARCHAR(8), 
	traffic_limit_period_days INTEGER, 
	description_template VARCHAR(255), 
	sort_order INTEGER NOT NULL, 
	is_builtin BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_client_template_node_name UNIQUE (node_id, name), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE config_tags (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	color VARCHAR(16), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_config_tag_node_name UNIQUE (node_id, name), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE connection_count_samples (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	openvpn_count INTEGER NOT NULL, 
	wireguard_count INTEGER NOT NULL, 
	amneziawg2_count INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE node_resource_sample (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	cpu_percent FLOAT NOT NULL, 
	memory_percent FLOAT NOT NULL, 
	memory_used_mb INTEGER NOT NULL, 
	memory_total_mb INTEGER NOT NULL, 
	disk_percent FLOAT NOT NULL, 
	load_1 FLOAT, 
	load_5 FLOAT, 
	load_15 FLOAT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE node_sync_groups (
	id INTEGER NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	shared_domain VARCHAR(255) NOT NULL, 
	shared_domain_wireguard VARCHAR(255), 
	primary_node_id INTEGER NOT NULL, 
	replica_node_ids TEXT NOT NULL, 
	sync_mode VARCHAR(32) NOT NULL, 
	sync_status VARCHAR(7) NOT NULL, 
	last_sync_at DATETIME, 
	last_verify_at DATETIME, 
	last_sync_task_id VARCHAR(32), 
	last_sync_error TEXT, 
	last_verify_result TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(primary_node_id) REFERENCES nodes (id)
);
CREATE TABLE nodes (
	id INTEGER NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	host VARCHAR(255) NOT NULL, 
	port INTEGER NOT NULL, 
	api_key_hash VARCHAR(255) NOT NULL, 
	api_key_encrypted VARCHAR(512) NOT NULL, 
	status VARCHAR(7) NOT NULL, 
	last_seen_at DATETIME, 
	is_local BOOLEAN NOT NULL, 
	mtls_enabled BOOLEAN NOT NULL, 
	transport VARCHAR(16) NOT NULL, 
	ssh_host VARCHAR(255), 
	ssh_port INTEGER NOT NULL, 
	ssh_username VARCHAR(128), 
	ssh_private_key_encrypted TEXT NOT NULL, 
	ssh_passphrase_encrypted TEXT NOT NULL, 
	ssh_remote_agent_host VARCHAR(255) NOT NULL, 
	ssh_remote_agent_port INTEGER, 
	ssh_host_key TEXT NOT NULL, 
	node_kind VARCHAR(16) NOT NULL, 
	destination_ip VARCHAR(64), 
	linked_vpn_node_id INTEGER, 
	node_metadata TEXT NOT NULL, 
	openvpn_remote_hosts TEXT, 
	wireguard_use_first_remote BOOLEAN NOT NULL, 
	openvpn_multihome BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(linked_vpn_node_id) REFERENCES nodes (id)
);
CREATE TABLE openvpn_access_policy (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	client_name VARCHAR(64) NOT NULL, 
	access_until DATETIME, 
	is_temp_blocked BOOLEAN NOT NULL, 
	is_permanent_blocked BOOLEAN NOT NULL, 
	block_reason VARCHAR(32), 
	block_started_at DATETIME, 
	block_days INTEGER, 
	block_until DATETIME, 
	traffic_limit_bytes BIGINT, 
	traffic_limit_period_days INTEGER, 
	updated_by VARCHAR(64), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ovpn_access_node_client UNIQUE (node_id, client_name), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE panel_resource_sample (
	id INTEGER NOT NULL, 
	backend_cpu_percent FLOAT NOT NULL, 
	backend_memory_mb INTEGER NOT NULL, 
	backend_workers INTEGER NOT NULL, 
	nginx_memory_mb INTEGER, 
	watchdog_memory_mb INTEGER, 
	frontend_dev_memory_mb INTEGER, 
	total_panel_memory_mb INTEGER NOT NULL, 
	local_node_memory_mb INTEGER NOT NULL, 
	node_agent_memory_mb INTEGER NOT NULL, 
	managed_vpn_memory_mb INTEGER NOT NULL, 
	local_vpn_core_memory_mb INTEGER NOT NULL, 
	legacy_antizapret_memory_mb INTEGER NOT NULL, 
	total_stack_memory_mb INTEGER NOT NULL, 
	host_cpu_percent FLOAT NOT NULL, 
	host_memory_percent FLOAT NOT NULL, 
	host_memory_used_mb INTEGER NOT NULL, 
	host_memory_total_mb INTEGER NOT NULL, 
	host_disk_percent FLOAT NOT NULL, 
	host_load_1 FLOAT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE provider_asn (
	id INTEGER NOT NULL, 
	provider_key VARCHAR(64) NOT NULL, 
	asn INTEGER NOT NULL, 
	source VARCHAR(64), 
	active BOOLEAN NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	error VARCHAR(512), 
	prefix_count INTEGER NOT NULL, 
	discovered_at DATETIME NOT NULL, 
	last_seen_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_provider_asn_key_asn UNIQUE (provider_key, asn)
);
CREATE TABLE provider_asn_snapshot (
	id INTEGER NOT NULL, 
	refresh_log_id INTEGER NOT NULL, 
	provider_key VARCHAR(64) NOT NULL, 
	asn INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	prefix_count INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_provider_asn_snapshot UNIQUE (refresh_log_id, provider_key, asn), 
	FOREIGN KEY(refresh_log_id) REFERENCES cidr_db_refresh_log (id)
);
CREATE TABLE provider_meta (
	id INTEGER NOT NULL, 
	provider_key VARCHAR(64) NOT NULL, 
	cidr_count INTEGER NOT NULL, 
	last_refreshed_at DATETIME, 
	refresh_status VARCHAR(16) NOT NULL, 
	refresh_error VARCHAR(512), 
	source_used VARCHAR(128), 
	expected_asn_min INTEGER NOT NULL, 
	asn_count INTEGER NOT NULL, 
	active_asn_count INTEGER NOT NULL, 
	anomaly_level VARCHAR(16) NOT NULL, 
	anomaly_reason VARCHAR(512), 
	PRIMARY KEY (id)
);
CREATE TABLE qr_download_audit_logs (
	id INTEGER NOT NULL, 
	token_id INTEGER, 
	event_type VARCHAR(32) NOT NULL, 
	actor_user_id INTEGER, 
	actor_username VARCHAR(64), 
	remote_addr VARCHAR(64), 
	details TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(token_id) REFERENCES qr_download_tokens (id), 
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
);
CREATE TABLE qr_download_tokens (
	id INTEGER NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	config_type VARCHAR(16) NOT NULL, 
	config_name VARCHAR(255) NOT NULL, 
	file_path VARCHAR(512) NOT NULL, 
	created_by_user_id INTEGER, 
	expires_at DATETIME NOT NULL, 
	max_downloads INTEGER NOT NULL, 
	download_count INTEGER NOT NULL, 
	pin_hash VARCHAR(64), 
	used_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by_user_id) REFERENCES users (id)
);
CREATE TABLE refresh_tokens (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE traffic_session_state (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	session_key VARCHAR(512) NOT NULL, 
	profile VARCHAR(64) NOT NULL, 
	common_name VARCHAR(128) NOT NULL, 
	real_address VARCHAR(64), 
	virtual_address VARCHAR(64), 
	connected_since_ts INTEGER NOT NULL, 
	last_bytes_received INTEGER NOT NULL, 
	last_bytes_sent INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	last_seen_at DATETIME, 
	ended_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE unlock_code_redemptions (
	id INTEGER NOT NULL, 
	code_id INTEGER NOT NULL, 
	client_name VARCHAR(64) NOT NULL, 
	node_id INTEGER NOT NULL, 
	redeemed_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_unlock_code_redemptions_code_client_node UNIQUE (code_id, client_name, node_id), 
	FOREIGN KEY(code_id) REFERENCES unlock_codes (id) ON DELETE CASCADE, 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE unlock_codes (
	id INTEGER NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	grant_days INTEGER NOT NULL, 
	protocols TEXT NOT NULL, 
	mode VARCHAR(8) NOT NULL, 
	max_redemptions INTEGER NOT NULL, 
	redemption_count INTEGER NOT NULL, 
	allowed_client_names TEXT NOT NULL, 
	code_expires_at DATETIME, 
	created_by_user_id INTEGER, 
	created_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_unlock_codes_code UNIQUE (code), 
	CONSTRAINT ck_unlock_codes_code_len CHECK (length(code) BETWEEN 8 AND 32), 
	CONSTRAINT ck_unlock_codes_mode CHECK (mode IN ('single', 'multi')), 
	FOREIGN KEY(created_by_user_id) REFERENCES users (id)
);
CREATE TABLE user_action_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	username VARCHAR(64), 
	action VARCHAR(64) NOT NULL, 
	details TEXT, 
	remote_addr VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE user_config_access (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	config_group VARCHAR(64) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_config_group UNIQUE (user_id, config_group), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE user_reminder_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	reminder_type VARCHAR(32) NOT NULL, 
	dedup_key VARCHAR(128) NOT NULL, 
	sent_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_reminder_dedup UNIQUE (user_id, reminder_type, dedup_key), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE user_traffic_sample (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	common_name VARCHAR(128) NOT NULL, 
	network_type VARCHAR(16) NOT NULL, 
	protocol_type VARCHAR(16) NOT NULL, 
	delta_received INTEGER NOT NULL, 
	delta_sent INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE user_traffic_stat_protocol (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	common_name VARCHAR(128) NOT NULL, 
	protocol_type VARCHAR(16) NOT NULL, 
	total_received INTEGER NOT NULL, 
	total_sent INTEGER NOT NULL, 
	total_received_vpn INTEGER NOT NULL, 
	total_sent_vpn INTEGER NOT NULL, 
	total_received_antizapret INTEGER NOT NULL, 
	total_sent_antizapret INTEGER NOT NULL, 
	total_sessions INTEGER NOT NULL, 
	first_seen_at DATETIME, 
	last_seen_at DATETIME, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_traffic_node_client_proto UNIQUE (node_id, common_name, protocol_type), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(5) NOT NULL, 
	theme VARCHAR(16) NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	last_client_timezone VARCHAR(64) NOT NULL, 
	noc_daily_time VARCHAR(5) NOT NULL, 
	noc_weekly_dow VARCHAR(1) NOT NULL, 
	noc_weekly_time VARCHAR(5) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	must_change_password BOOLEAN NOT NULL, 
	totp_secret_encrypted VARCHAR(512), 
	totp_enabled BOOLEAN NOT NULL, 
	totp_backup_codes_encrypted VARCHAR(1024), 
	telegram_id VARCHAR(32), 
	tg_notify_events TEXT, 
	config_quota INTEGER, 
	can_create_configs BOOLEAN NOT NULL, 
	visible_vpn_profiles TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE vpn_config_tag_links (
	id INTEGER NOT NULL, 
	vpn_config_id INTEGER NOT NULL, 
	tag_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_config_tag_link UNIQUE (vpn_config_id, tag_id), 
	FOREIGN KEY(vpn_config_id) REFERENCES vpn_configs (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES config_tags (id) ON DELETE CASCADE
);
CREATE TABLE vpn_configs (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	client_name VARCHAR(32) NOT NULL, 
	vpn_type VARCHAR(10) NOT NULL, 
	owner_id INTEGER NOT NULL, 
	cert_expire_days INTEGER, 
	cert_expires_at DATETIME, 
	expires_at DATETIME, 
	description VARCHAR(255), 
	sync_group_id INTEGER, 
	ha_primary_config_id INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_node_client_vpn_type UNIQUE (node_id, client_name, vpn_type), 
	FOREIGN KEY(node_id) REFERENCES nodes (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	FOREIGN KEY(sync_group_id) REFERENCES node_sync_groups (id), 
	FOREIGN KEY(ha_primary_config_id) REFERENCES vpn_configs (id)
);
CREATE TABLE webauthn_credentials (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	credential_id VARCHAR(512) NOT NULL, 
	public_key TEXT NOT NULL, 
	sign_count INTEGER NOT NULL, 
	transports TEXT, 
	aaguid VARCHAR(64), 
	nickname VARCHAR(128) NOT NULL, 
	created_at DATETIME NOT NULL, 
	last_used_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_webauthn_credential_id UNIQUE (credential_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE webhook_delivery (
	id INTEGER NOT NULL, 
	event_action VARCHAR(64) NOT NULL, 
	payload_json TEXT NOT NULL, 
	url VARCHAR(512) NOT NULL, 
	destination_type VARCHAR(16) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	attempts INTEGER NOT NULL, 
	last_status_code INTEGER, 
	last_error TEXT, 
	next_retry_at DATETIME, 
	created_at DATETIME NOT NULL, 
	delivered_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE wg_access_policy (
	id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	client_name VARCHAR(64) NOT NULL, 
	expires_at DATETIME, 
	is_temp_blocked BOOLEAN NOT NULL, 
	is_permanent_blocked BOOLEAN NOT NULL, 
	block_reason VARCHAR(32), 
	block_started_at DATETIME, 
	block_days INTEGER, 
	block_until DATETIME, 
	traffic_limit_bytes BIGINT, 
	traffic_limit_period_days INTEGER, 
	updated_by VARCHAR(64), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_wg_access_node_client UNIQUE (node_id, client_name), 
	FOREIGN KEY(node_id) REFERENCES nodes (id)
);
CREATE INDEX ix_active_web_session_last_seen_at ON active_web_session (last_seen_at);
CREATE UNIQUE INDEX ix_active_web_session_session_id ON active_web_session (session_id);
CREATE INDEX ix_active_web_session_username ON active_web_session (username);
CREATE INDEX ix_alert_rules_node_id ON alert_rules (node_id);
CREATE INDEX ix_amneziawg2_access_policies_client_name ON amneziawg2_access_policies (client_name);
CREATE INDEX ix_amneziawg2_access_policies_node_id ON amneziawg2_access_policies (node_id);
CREATE UNIQUE INDEX ix_antifilter_cidr_cidr ON antifilter_cidr (cidr);
CREATE UNIQUE INDEX ix_app_settings_key ON app_settings ("key");
CREATE INDEX ix_background_task_created_at ON background_task (created_at);
CREATE INDEX ix_background_task_created_by_username ON background_task (created_by_username);
CREATE INDEX ix_background_task_status ON background_task (status);
CREATE INDEX ix_background_task_task_type ON background_task (task_type);
CREATE INDEX ix_cidr_db_refresh_log_started_at ON cidr_db_refresh_log (started_at);
CREATE INDEX ix_client_portal_tokens_client_name ON client_portal_tokens (client_name);
CREATE INDEX ix_client_portal_tokens_node_id ON client_portal_tokens (node_id);
CREATE UNIQUE INDEX ix_client_portal_tokens_token ON client_portal_tokens (token);
CREATE INDEX ix_client_templates_node_id ON client_templates (node_id);
CREATE INDEX ix_config_tags_name ON config_tags (name);
CREATE INDEX ix_config_tags_node_id ON config_tags (node_id);
CREATE INDEX ix_connection_count_samples_created_at ON connection_count_samples (created_at);
CREATE INDEX ix_connection_count_samples_node_id ON connection_count_samples (node_id);
CREATE INDEX ix_node_resource_sample_created_at ON node_resource_sample (created_at);
CREATE INDEX ix_node_resource_sample_node_id ON node_resource_sample (node_id);
CREATE INDEX ix_node_sync_groups_id ON node_sync_groups (id);
CREATE INDEX ix_node_sync_groups_primary_node_id ON node_sync_groups (primary_node_id);
CREATE INDEX ix_nodes_id ON nodes (id);
CREATE INDEX ix_nodes_linked_vpn_node_id ON nodes (linked_vpn_node_id);
CREATE INDEX ix_openvpn_access_policy_client_name ON openvpn_access_policy (client_name);
CREATE INDEX ix_openvpn_access_policy_node_id ON openvpn_access_policy (node_id);
CREATE INDEX ix_panel_resource_sample_created_at ON panel_resource_sample (created_at);
CREATE INDEX ix_provider_asn_active ON provider_asn (active);
CREATE INDEX ix_provider_asn_asn ON provider_asn (asn);
CREATE INDEX ix_provider_asn_last_seen_at ON provider_asn (last_seen_at);
CREATE INDEX ix_provider_asn_provider_key ON provider_asn (provider_key);
CREATE INDEX ix_provider_asn_snapshot_asn ON provider_asn_snapshot (asn);
CREATE INDEX ix_provider_asn_snapshot_created_at ON provider_asn_snapshot (created_at);
CREATE INDEX ix_provider_asn_snapshot_provider_key ON provider_asn_snapshot (provider_key);
CREATE INDEX ix_provider_asn_snapshot_refresh_log_id ON provider_asn_snapshot (refresh_log_id);
CREATE INDEX ix_provider_meta_anomaly_level ON provider_meta (anomaly_level);
CREATE INDEX ix_provider_meta_last_refreshed_at ON provider_meta (last_refreshed_at);
CREATE UNIQUE INDEX ix_provider_meta_provider_key ON provider_meta (provider_key);
CREATE UNIQUE INDEX ix_qr_download_tokens_token_hash ON qr_download_tokens (token_hash);
CREATE UNIQUE INDEX ix_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX ix_traffic_session_state_common_name ON traffic_session_state (common_name);
CREATE INDEX ix_traffic_session_state_node_id ON traffic_session_state (node_id);
CREATE UNIQUE INDEX ix_traffic_session_state_session_key ON traffic_session_state (session_key);
CREATE INDEX ix_unlock_code_redemptions_client_name ON unlock_code_redemptions (client_name);
CREATE INDEX ix_unlock_code_redemptions_code_id ON unlock_code_redemptions (code_id);
CREATE INDEX ix_unlock_code_redemptions_node_id ON unlock_code_redemptions (node_id);
CREATE INDEX ix_unlock_codes_code ON unlock_codes (code);
CREATE INDEX ix_user_action_logs_created_at ON user_action_logs (created_at);
CREATE INDEX ix_user_config_access_user_id ON user_config_access (user_id);
CREATE INDEX ix_user_reminder_logs_reminder_type ON user_reminder_logs (reminder_type);
CREATE INDEX ix_user_reminder_logs_sent_at ON user_reminder_logs (sent_at);
CREATE INDEX ix_user_reminder_logs_user_id ON user_reminder_logs (user_id);
CREATE INDEX ix_user_traffic_sample_common_name ON user_traffic_sample (common_name);
CREATE INDEX ix_user_traffic_sample_created_at ON user_traffic_sample (created_at);
CREATE INDEX ix_user_traffic_sample_node_created ON user_traffic_sample (node_id, created_at);
CREATE INDEX ix_user_traffic_sample_node_id ON user_traffic_sample (node_id);
CREATE INDEX ix_user_traffic_stat_protocol_common_name ON user_traffic_stat_protocol (common_name);
CREATE INDEX ix_user_traffic_stat_protocol_node_id ON user_traffic_stat_protocol (node_id);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_telegram_id ON users (telegram_id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_vpn_config_tag_links_tag_id ON vpn_config_tag_links (tag_id);
CREATE INDEX ix_vpn_config_tag_links_vpn_config_id ON vpn_config_tag_links (vpn_config_id);
CREATE INDEX ix_vpn_configs_client_name ON vpn_configs (client_name);
CREATE INDEX ix_vpn_configs_ha_primary_config_id ON vpn_configs (ha_primary_config_id);
CREATE INDEX ix_vpn_configs_id ON vpn_configs (id);
CREATE INDEX ix_vpn_configs_node_id ON vpn_configs (node_id);
CREATE INDEX ix_vpn_configs_sync_group_id ON vpn_configs (sync_group_id);
CREATE INDEX ix_webauthn_credentials_credential_id ON webauthn_credentials (credential_id);
CREATE INDEX ix_webauthn_credentials_user_id ON webauthn_credentials (user_id);
CREATE INDEX ix_webhook_delivery_created_at ON webhook_delivery (created_at);
CREATE INDEX ix_webhook_delivery_destination_type ON webhook_delivery (destination_type);
CREATE INDEX ix_webhook_delivery_event_action ON webhook_delivery (event_action);
CREATE INDEX ix_webhook_delivery_next_retry_at ON webhook_delivery (next_retry_at);
CREATE INDEX ix_webhook_delivery_status ON webhook_delivery (status);
CREATE INDEX ix_wg_access_policy_client_name ON wg_access_policy (client_name);
CREATE INDEX ix_wg_access_policy_node_id ON wg_access_policy (node_id);
CREATE UNIQUE INDEX uq_client_portal_tokens_active_node_client ON client_portal_tokens (node_id, client_name) WHERE revoked_at IS NULL;
