REVOKE ALL PRIVILEGES ON wp.* FROM 'import_reader'@'%';
GRANT SELECT ON wp.* TO 'import_reader'@'%';
