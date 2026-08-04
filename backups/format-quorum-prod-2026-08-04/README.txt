This directory contains a point-in-time backup of the production Docker volumes.

Archives:
- format-quorum_tests_data.tar.gz: tests, including edits made in the production UI
- format-quorum_config_data.tar.gz: published config history, shadows and custom formatter metadata
- format-quorum_clang_versions.tar.gz: installed formatter versions
- format-quorum_caddy_data.tar.gz: Caddy TLS data
- format-quorum_caddy_config.tar.gz: Caddy configuration data

The local docker-compose.yml uses the first three archives through named volumes:
format-quorum-local_tests_data, format-quorum-local_config_data and
format-quorum-local_clang_versions.
