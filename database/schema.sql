-- ============================================================================
-- Warehouse Management System — MySQL 8 schema
-- Generated from backend/app/models.py (python -m app.gen_schema). Do not edit by hand.
-- ============================================================================
CREATE DATABASE IF NOT EXISTS wms CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE wms;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `audit_log`;
DROP TABLE IF EXISTS `company`;
DROP TABLE IF EXISTS `material`;
DROP TABLE IF EXISTS `number_range`;
DROP TABLE IF EXISTS `warehouse`;
DROP TABLE IF EXISTS `activity_area`;
DROP TABLE IF EXISTS `asn`;
DROP TABLE IF EXISTS `bin_type`;
DROP TABLE IF EXISTS `bom`;
DROP TABLE IF EXISTS `crossdock_order`;
DROP TABLE IF EXISTS `door`;
DROP TABLE IF EXISTS `plant`;
DROP TABLE IF EXISTS `queue`;
DROP TABLE IF EXISTS `resource_type`;
DROP TABLE IF EXISTS `stock_transfer`;
DROP TABLE IF EXISTS `storage_type`;
DROP TABLE IF EXISTS `warehouse_config`;
DROP TABLE IF EXISTS `wave`;
DROP TABLE IF EXISTS `work_center`;
DROP TABLE IF EXISTS `wt_document`;
DROP TABLE IF EXISTS `xdock_event`;
DROP TABLE IF EXISTS `asn_line`;
DROP TABLE IF EXISTS `bom_item`;
DROP TABLE IF EXISTS `crossdock_order_line`;
DROP TABLE IF EXISTS `document_shortage`;
DROP TABLE IF EXISTS `resource`;
DROP TABLE IF EXISTS `sales_order`;
DROP TABLE IF EXISTS `stock_transfer_event`;
DROP TABLE IF EXISTS `stock_transfer_line`;
DROP TABLE IF EXISTS `stock_transfer_shipped`;
DROP TABLE IF EXISTS `storage_location`;
DROP TABLE IF EXISTS `storage_section`;
DROP TABLE IF EXISTS `warehouse_order`;
DROP TABLE IF EXISTS `rack`;
DROP TABLE IF EXISTS `sales_order_line`;
DROP TABLE IF EXISTS `warehouse_task`;
DROP TABLE IF EXISTS `bin`;
DROP TABLE IF EXISTS `stock`;

CREATE TABLE audit_log (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT, 
	ts DATETIME NOT NULL DEFAULT (now()), 
	`role` VARCHAR(12) NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	detail VARCHAR(500) NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_audit_log_ts ON audit_log (ts);
CREATE INDEX ix_audit_log_warehouse_id ON audit_log (warehouse_id);

CREATE TABLE company (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	legal_name VARCHAR(200) NOT NULL, 
	pan VARCHAR(10) NOT NULL, 
	cin VARCHAR(21) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	country VARCHAR(2) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE material (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(150) NOT NULL, 
	uom VARCHAR(5) NOT NULL, 
	type VARCHAR(5) NOT NULL, 
	tracking VARCHAR(6) NOT NULL, 
	weight NUMERIC(18, 4) NOT NULL, 
	volume NUMERIC(18, 4) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE number_range (
	warehouse_id BIGINT NOT NULL, 
	object VARCHAR(10) NOT NULL, 
	last_no BIGINT NOT NULL, 
	PRIMARY KEY (warehouse_id, object)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE warehouse (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	type VARCHAR(8) NOT NULL, 
	trade_name VARCHAR(150) NOT NULL, 
	addr_line1 VARCHAR(200) NOT NULL, 
	addr_line2 VARCHAR(200) NOT NULL, 
	city VARCHAR(100) NOT NULL, 
	district VARCHAR(100) NOT NULL, 
	state_code VARCHAR(2) NOT NULL, 
	pin VARCHAR(6) NOT NULL, 
	country VARCHAR(60) NOT NULL, 
	gstin VARCHAR(15) NOT NULL, 
	contact VARCHAR(100) NOT NULL, 
	phone VARCHAR(40) NOT NULL, 
	email VARCHAR(150) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	PRIMARY KEY (id), 
	UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_warehouse_gstin ON warehouse (gstin);

CREATE TABLE activity_area (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	activity VARCHAR(4) NOT NULL, 
	path_sort VARCHAR(6) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_activity_area_warehouse_id ON activity_area (warehouse_id);

CREATE TABLE asn (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	number VARCHAR(20) NOT NULL, 
	vendor VARCHAR(150) NOT NULL, 
	eta DATE, 
	status VARCHAR(10) NOT NULL, 
	transfer_id BIGINT, 
	hub_crossdock BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, number), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_asn_transfer_id ON asn (transfer_id);
CREATE INDEX ix_asn_warehouse_id ON asn (warehouse_id);

CREATE TABLE bin_type (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	max_qty NUMERIC(18, 4) NOT NULL, 
	max_weight NUMERIC(18, 4) NOT NULL, 
	max_volume NUMERIC(18, 4) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_bin_type_warehouse_id ON bin_type (warehouse_id);

CREATE TABLE bom (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	parent_material_id BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (parent_material_id), 
	FOREIGN KEY(parent_material_id) REFERENCES material (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE crossdock_order (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	number VARCHAR(20) NOT NULL, 
	kind VARCHAR(4) NOT NULL, 
	from_party VARCHAR(150) NOT NULL, 
	to_party VARCHAR(150) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	document_id BIGINT, 
	transfer_id BIGINT, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	received_at DATETIME, 
	ready_at DATETIME, 
	shipped_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, number), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_crossdock_order_warehouse_id ON crossdock_order (warehouse_id);

CREATE TABLE door (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(12) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	direction VARCHAR(4) NOT NULL, 
	bin_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_door_warehouse_id ON door (warehouse_id);

CREATE TABLE plant (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	company_id BIGINT NOT NULL, 
	city VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(company_id) REFERENCES company (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_plant_company_id ON plant (company_id);

CREATE TABLE queue (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(12) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	activity_area_ids JSON NOT NULL, 
	task_types JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_queue_warehouse_id ON queue (warehouse_id);

CREATE TABLE resource_type (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	max_level INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_resource_type_warehouse_id ON resource_type (warehouse_id);

CREATE TABLE stock_transfer (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	number VARCHAR(20) NOT NULL, 
	from_wh_id BIGINT NOT NULL, 
	via_wh_id BIGINT, 
	to_wh_id BIGINT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	done_at DATETIME, 
	source_order_id BIGINT, 
	hub_asn_id BIGINT, 
	hub_xd_id BIGINT, 
	dest_asn_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (number), 
	FOREIGN KEY(from_wh_id) REFERENCES warehouse (id), 
	FOREIGN KEY(via_wh_id) REFERENCES warehouse (id), 
	FOREIGN KEY(to_wh_id) REFERENCES warehouse (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_stock_transfer_from_wh_id ON stock_transfer (from_wh_id);
CREATE INDEX ix_stock_transfer_to_wh_id ON stock_transfer (to_wh_id);
CREATE INDEX ix_stock_transfer_via_wh_id ON stock_transfer (via_wh_id);

CREATE TABLE storage_type (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	`role` VARCHAR(10) NOT NULL, 
	putaway_rank INTEGER NOT NULL, 
	pick_rank INTEGER NOT NULL, 
	mixed_storage BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_storage_type_warehouse_id ON storage_type (warehouse_id);

CREATE TABLE warehouse_config (
	warehouse_id BIGINT NOT NULL, 
	putaway_steps INTEGER NOT NULL, 
	putaway_strategy VARCHAR(12) NOT NULL, 
	pick_steps INTEGER NOT NULL, 
	pick_strategy VARCHAR(8) NOT NULL, 
	stage_in_bin_id BIGINT, 
	stage_out_bin_id BIGINT, 
	explode_bom BOOL NOT NULL, 
	xdock_opportunistic BOOL NOT NULL, 
	xd_in_bin_id BIGINT, 
	xd_out_bin_id BIGINT, 
	wo_max_tasks INTEGER NOT NULL, 
	PRIMARY KEY (warehouse_id), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE wave (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	number VARCHAR(20) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, number), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_wave_warehouse_id ON wave (warehouse_id);

CREATE TABLE work_center (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(12) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	kind VARCHAR(4) NOT NULL, 
	bin_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_work_center_warehouse_id ON work_center (warehouse_id);

CREATE TABLE wt_document (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	number VARCHAR(20) NOT NULL, 
	type VARCHAR(8) NOT NULL, 
	steps INTEGER NOT NULL, 
	stage_bin_id BIGINT, 
	strategy VARCHAR(20) NOT NULL, 
	source VARCHAR(100) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	wave_id BIGINT, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, number), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_wt_document_warehouse_id ON wt_document (warehouse_id);

CREATE TABLE xdock_event (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	asn_number VARCHAR(20) NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	to_bin_id BIGINT NOT NULL, 
	pick_doc_number VARCHAR(20) NOT NULL, 
	tracking_no VARCHAR(40) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	PRIMARY KEY (id), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_xdock_event_material_id ON xdock_event (material_id);
CREATE INDEX ix_xdock_event_warehouse_id ON xdock_event (warehouse_id);

CREATE TABLE asn_line (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	asn_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	tracking_no VARCHAR(40) NOT NULL, 
	expiry DATE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asn_id) REFERENCES asn (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_asn_line_asn_id ON asn_line (asn_id);
CREATE INDEX ix_asn_line_material_id ON asn_line (material_id);

CREATE TABLE bom_item (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	bom_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(bom_id) REFERENCES bom (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_bom_item_bom_id ON bom_item (bom_id);
CREATE INDEX ix_bom_item_material_id ON bom_item (material_id);

CREATE TABLE crossdock_order_line (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	order_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	tracking_no VARCHAR(40) NOT NULL, 
	expiry DATE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES crossdock_order (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_crossdock_order_line_material_id ON crossdock_order_line (material_id);
CREATE INDEX ix_crossdock_order_line_order_id ON crossdock_order_line (order_id);

CREATE TABLE document_shortage (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	document_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	level INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES wt_document (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_document_shortage_document_id ON document_shortage (document_id);
CREATE INDEX ix_document_shortage_material_id ON document_shortage (material_id);

CREATE TABLE resource (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(20) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	resource_type_id BIGINT, 
	queue_ids JSON NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	current_wo_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(resource_type_id) REFERENCES resource_type (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_resource_resource_type_id ON resource (resource_type_id);
CREATE INDEX ix_resource_warehouse_id ON resource (warehouse_id);

CREATE TABLE sales_order (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	number VARCHAR(20) NOT NULL, 
	customer VARCHAR(150) NOT NULL, 
	order_date DATE, 
	status VARCHAR(10) NOT NULL, 
	wave_id BIGINT, 
	transfer_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, number), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(wave_id) REFERENCES wave (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_sales_order_transfer_id ON sales_order (transfer_id);
CREATE INDEX ix_sales_order_warehouse_id ON sales_order (warehouse_id);
CREATE INDEX ix_sales_order_wave_id ON sales_order (wave_id);

CREATE TABLE stock_transfer_event (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	transfer_id BIGINT NOT NULL, 
	ts DATETIME NOT NULL DEFAULT (now()), 
	message VARCHAR(300) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(transfer_id) REFERENCES stock_transfer (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_stock_transfer_event_transfer_id ON stock_transfer_event (transfer_id);

CREATE TABLE stock_transfer_line (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	transfer_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(transfer_id) REFERENCES stock_transfer (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_stock_transfer_line_material_id ON stock_transfer_line (material_id);
CREATE INDEX ix_stock_transfer_line_transfer_id ON stock_transfer_line (transfer_id);

CREATE TABLE stock_transfer_shipped (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	transfer_id BIGINT NOT NULL, 
	leg INTEGER NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	tracking_no VARCHAR(40) NOT NULL, 
	expiry DATE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(transfer_id) REFERENCES stock_transfer (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_stock_transfer_shipped_material_id ON stock_transfer_shipped (material_id);
CREATE INDEX ix_stock_transfer_shipped_transfer_id ON stock_transfer_shipped (transfer_id);

CREATE TABLE storage_location (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	plant_id BIGINT NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	warehouse_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (plant_id, code), 
	FOREIGN KEY(plant_id) REFERENCES plant (id) ON DELETE CASCADE, 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_storage_location_plant_id ON storage_location (plant_id);
CREATE INDEX ix_storage_location_warehouse_id ON storage_location (warehouse_id);

CREATE TABLE storage_section (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	storage_type_id BIGINT NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (storage_type_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(storage_type_id) REFERENCES storage_type (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_storage_section_storage_type_id ON storage_section (storage_type_id);
CREATE INDEX ix_storage_section_warehouse_id ON storage_section (warehouse_id);

CREATE TABLE warehouse_order (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	number VARCHAR(20) NOT NULL, 
	document_id BIGINT NOT NULL, 
	type VARCHAR(8) NOT NULL, 
	area_key VARCHAR(30) NOT NULL, 
	queue_id BIGINT, 
	resource_id BIGINT, 
	status VARCHAR(12) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT (now()), 
	started_at DATETIME, 
	done_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, number), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(document_id) REFERENCES wt_document (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_warehouse_order_document_id ON warehouse_order (document_id);
CREATE INDEX ix_warehouse_order_warehouse_id ON warehouse_order (warehouse_id);

CREATE TABLE rack (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(20) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	storage_type_id BIGINT NOT NULL, 
	section_id BIGINT, 
	bin_type_id BIGINT, 
	activity_area_id BIGINT, 
	pick_face BOOL NOT NULL, 
	x1 INTEGER NOT NULL, 
	y1 INTEGER NOT NULL, 
	x2 INTEGER NOT NULL, 
	y2 INTEGER NOT NULL, 
	aisle_from INTEGER NOT NULL, 
	aisle_to INTEGER NOT NULL, 
	aisle_gap INTEGER NOT NULL, 
	pos_from INTEGER NOT NULL, 
	pos_step INTEGER NOT NULL, 
	level_from INTEGER NOT NULL, 
	level_to INTEGER NOT NULL, 
	pattern VARCHAR(60) NOT NULL, 
	pad INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(storage_type_id) REFERENCES storage_type (id), 
	FOREIGN KEY(section_id) REFERENCES storage_section (id) ON DELETE SET NULL, 
	FOREIGN KEY(bin_type_id) REFERENCES bin_type (id) ON DELETE SET NULL, 
	FOREIGN KEY(activity_area_id) REFERENCES activity_area (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_rack_activity_area_id ON rack (activity_area_id);
CREATE INDEX ix_rack_bin_type_id ON rack (bin_type_id);
CREATE INDEX ix_rack_section_id ON rack (section_id);
CREATE INDEX ix_rack_storage_type_id ON rack (storage_type_id);
CREATE INDEX ix_rack_warehouse_id ON rack (warehouse_id);

CREATE TABLE sales_order_line (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	order_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES sales_order (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_sales_order_line_material_id ON sales_order_line (material_id);
CREATE INDEX ix_sales_order_line_order_id ON sales_order_line (order_id);

CREATE TABLE warehouse_task (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	document_id BIGINT NOT NULL, 
	line_no INTEGER NOT NULL, 
	wt_number BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	qty NUMERIC(18, 4) NOT NULL, 
	tracking_no VARCHAR(40) NOT NULL, 
	expiry DATE, 
	source_bin_id BIGINT, 
	dest_bin_id BIGINT, 
	stock_id BIGINT, 
	level INTEGER NOT NULL, 
	orders_ref VARCHAR(200) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	wo_id BIGINT, 
	confirmed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(document_id) REFERENCES wt_document (id) ON DELETE CASCADE, 
	FOREIGN KEY(material_id) REFERENCES material (id), 
	FOREIGN KEY(wo_id) REFERENCES warehouse_order (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_warehouse_task_document_id ON warehouse_task (document_id);
CREATE INDEX ix_warehouse_task_material_id ON warehouse_task (material_id);
CREATE INDEX ix_warehouse_task_warehouse_id ON warehouse_task (warehouse_id);
CREATE INDEX ix_warehouse_task_wo_id ON warehouse_task (wo_id);

CREATE TABLE bin (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	storage_type_id BIGINT NOT NULL, 
	section_id BIGINT, 
	bin_type_id BIGINT, 
	activity_area_id BIGINT, 
	rack_id BIGINT, 
	x INTEGER NOT NULL, 
	y INTEGER NOT NULL, 
	z INTEGER NOT NULL, 
	max_qty NUMERIC(18, 4) NOT NULL, 
	max_weight NUMERIC(18, 4) NOT NULL, 
	max_volume NUMERIC(18, 4) NOT NULL, 
	blocked BOOL NOT NULL, 
	pick_face BOOL NOT NULL, 
	min_qty NUMERIC(18, 4) NOT NULL, 
	replen_to NUMERIC(18, 4) NOT NULL, 
	fixed_material_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (warehouse_id, code), 
	UNIQUE (warehouse_id, x, y, z), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(storage_type_id) REFERENCES storage_type (id), 
	FOREIGN KEY(section_id) REFERENCES storage_section (id) ON DELETE SET NULL, 
	FOREIGN KEY(bin_type_id) REFERENCES bin_type (id) ON DELETE SET NULL, 
	FOREIGN KEY(activity_area_id) REFERENCES activity_area (id) ON DELETE SET NULL, 
	FOREIGN KEY(rack_id) REFERENCES rack (id) ON DELETE SET NULL, 
	FOREIGN KEY(fixed_material_id) REFERENCES material (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_bin_activity_area_id ON bin (activity_area_id);
CREATE INDEX ix_bin_bin_type_id ON bin (bin_type_id);
CREATE INDEX ix_bin_fixed_material_id ON bin (fixed_material_id);
CREATE INDEX ix_bin_rack_id ON bin (rack_id);
CREATE INDEX ix_bin_section_id ON bin (section_id);
CREATE INDEX ix_bin_storage_type_id ON bin (storage_type_id);
CREATE INDEX ix_bin_warehouse_id ON bin (warehouse_id);

CREATE TABLE stock (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	warehouse_id BIGINT NOT NULL, 
	bin_id BIGINT NOT NULL, 
	material_id BIGINT NOT NULL, 
	batch VARCHAR(40) NOT NULL, 
	serial VARCHAR(40) NOT NULL, 
	expiry DATE, 
	qty NUMERIC(18, 4) NOT NULL, 
	gr_seq BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(warehouse_id) REFERENCES warehouse (id) ON DELETE CASCADE, 
	FOREIGN KEY(bin_id) REFERENCES bin (id), 
	FOREIGN KEY(material_id) REFERENCES material (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_stock_bin_id ON stock (bin_id);
CREATE INDEX ix_stock_material_id ON stock (material_id);
CREATE INDEX ix_stock_warehouse_id ON stock (warehouse_id);
CREATE INDEX ix_stock_wh_mat ON stock (warehouse_id, material_id);

SET FOREIGN_KEY_CHECKS = 1;
