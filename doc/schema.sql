DROP TABLE IF EXISTS plan;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS copies;

CREATE TABLE plan (
  master_ip varchar(15) NOT NULL,
  master_host varchar(255) NOT NULL,
  job_name varchar(255) NOT NULL,
  master_instance varchar(255) DEFAULT NULL,
  timestamp timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ignored tinyint(1) DEFAULT 0 NOT NULL,
  max_data_age int(11) DEFAULT 0 NOT NULL,
  max_backup_age int(11) DEFAULT 86400 NOT NULL,
  max_copy_time int(11) DEFAULT 3600 NOT NULL,
  note varchar(255),
  UNIQUE KEY (master_host, job_name, master_instance)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE jobs (
  job_id bigint NOT NULL AUTO_INCREMENT,
  host varchar(255) NOT NULL,
  name varchar(255) NOT NULL,
  instance varchar(255) DEFAULT '',
  master_host varchar(255) DEFAULT '',
  master_instance varchar(255) DEFAULT '',
  direction varchar(31) NOT NULL,
  start_time datetime NOT NULL,
  last_op_time timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  step enum('INIT', 'PRE', 'COPYING', 'POST', 'DONE') NOT NULL DEFAULT 'INIT',
  status enum('OK', 'WARNING', 'FAILED') NOT NULL DEFAULT 'OK',
  data_age int(10) DEFAULT 0,
  ack tinyint(1) DEFAULT '0',
  PRIMARY KEY (job_id),
  UNIQUE KEY (start_time, host, name, instance),
  KEY (host, name, instance)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE copies (
  job_id bigint NOT NULL,
  copy_id bigint NOT NULL AUTO_INCREMENT,
  destination varchar(31) NOT NULL,
  type varchar(31) NOT NULL,
  path varchar(1024) NOT NULL,
  status enum('INIT', 'COPYING', 'DONE', 'WARNING', 'FAILED') NOT NULL DEFAULT 'INIT',
  last_op_time timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (copy_id),
  UNIQUE KEY (job_id, destination)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

