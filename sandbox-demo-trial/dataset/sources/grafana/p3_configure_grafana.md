# Configure Grafana

Grafana uses default and custom configuration files to customize instances through configuration file modifications or environment variables.

## Configuration File Locations

Default settings are stored in `<WORKING DIRECTORY>/conf/defaults.ini`. Custom configuration files vary by operating system:

- **Linux (deb/RPM):** `/etc/grafana/grafana.ini`
- **Docker:** Refer to Docker-specific configuration documentation
- **Windows:** Create `custom.ini` in the same directory as `defaults.ini`
- **macOS:** `/opt/homebrew/etc/grafana/grafana.ini` or `/usr/local/etc/grafana/grafana.ini`
- **Grafana Cloud:** No local configuration file; contact support for setting changes

## Configuration Methods

### File-Based Configuration

Uncomment relevant sections in the INI file by removing semicolons (`;`) at line beginnings. Grafana ignores commented lines.

### Environment Variables

Override configuration using the pattern: `GF_<SECTION>_<KEY>`

All uppercase letters, periods, and dashes converted to underscores.

Example:
```bash
export GF_SECURITY_ADMIN_USER=owner
export GF_AUTH_GOOGLE_CLIENT_SECRET=newS3cretKey
```

### Variable Expansion

Grafana evaluates expressions using three providers:

- **`env` provider:** Expands environment variables using `$__env{VARIABLE}` or `${VARIABLE}`
- **`file` provider:** Reads file contents using `$__file{/path/to/file}`
- **`vault` provider:** Manages secrets with HashiCorp Vault (Enterprise only)

## Core Configuration Sections

### `[paths]`

- `data`: SQLite database and session storage location
- `logs`: Log file directory
- `plugins`: Plugin scanning directory
- `provisioning`: Configuration files directory
- `temp_data_lifetime`: Temporary image retention (default: `24h`)

### `[server]`

- `protocol`: `http`, `https`, `h2`, `socket`, or `socket_h2`
- `http_addr`: Host address (empty = `0.0.0.0`)
- `http_port`: Port binding (default: `3000`)
- `domain`: Domain for OAuth callbacks
- `root_url`: Full browser access URL
- `serve_from_sub_path`: Enable sub-path serving
- `enable_gzip`: Enable HTTP compression
- `cert_file`, `cert_key`: HTTPS certificate paths
- `cdn_url`: CDN asset root URL

### `[database]`

- `type`: `mysql`, `postgres`, or `sqlite3`
- `host`: Database server address
- `name`: Database name
- `user`, `password`: Database credentials
- `url`: Full connection string
- `max_idle_conn`, `max_open_conn`: Connection pooling
- `ssl_mode`: SSL configuration for Postgres/MySQL
- `log_queries`: Enable SQL logging

### `[security]`

- `admin_user`, `admin_password`: Default admin credentials
- `secret_key`: AES-256 encryption key for secrets
- `disable_gravatar`: Disable Gravatar profile images
- `cookie_secure`: Set for HTTPS deployments
- `cookie_samesite`: CSRF protection (`lax`, `strict`, `none`)
- `allow_embedding`: Control iframe embedding
- `strict_transport_security`: Enable HSTS
- `content_security_policy`: Add CSP headers
- `disable_brute_force_login_protection`: Login attempt limiting

### `[users]`

- `allow_sign_up`: Permit user registration
- `auto_assign_org`: Auto-add users to main organization
- `auto_assign_org_role`: Default role (`Viewer`, `Editor`, `Admin`)
- `verify_email_enabled`: Require email validation
- `default_theme`: `dark`, `light`, or `system`
- `default_language`: IETF language tag (default: `en-US`)

### `[auth]`

- `login_cookie_name`: Auth token cookie name
- `login_maximum_inactive_lifetime_duration`: Session inactivity timeout (default: `7d`)
- `login_maximum_lifetime_duration`: Max login duration (default: `30d`)
- `disable_login_form`: Hide login form for OAuth-only
- `oauth_state_cookie_max_age`: OAuth state cookie lifetime (default: `600s`)

Authentication providers include: `[auth.anonymous]`, `[auth.github]`, `[auth.gitlab]`, `[auth.google]`, `[auth.azuread]`, `[auth.okta]`, `[auth.generic_oauth]`, `[auth.ldap]`, `[auth.proxy]`, `[auth.jwt]`, `[auth.basic]`

### `[smtp]`

Email server configuration for notifications:

- `enabled`: Enable email functionality
- `host`: SMTP server address
- `user`, `password`: SMTP credentials
- `from_address`, `from_name`: Sender information
- `startTLS_policy`: `OpportunisticStartTLS`, `MandatoryStartTLS`, `NoStartTLS`

### `[analytics]`

- `enabled`: Enable usage analytics
- `reporting_enabled`: Send anonymous statistics
- `check_for_updates`: Check GitHub for new versions
- `google_analytics_ua_id`: Google Analytics tracking
- `rudderstack_write_key`: RudderStack event tracking

### `[dashboards]`

- `versions_to_keep`: Dashboard version retention (default: `20`)
- `min_refresh_interval`: Minimum dashboard refresh (default: `5s`)
- `default_home_dashboard_path`: Custom home dashboard location

### `[datasources]`

- `default_manage_alerts_ui_toggle`: Alert management UI default behavior
- Configuration for SQL datasources connection pooling

### `[unified_alerting]`

- `enabled`: Enable Grafana Alerting (default: `true`)
- `execute_alerts`: Enable rule execution (default: `true`)
- `evaluation_timeout`: Alert evaluation timeout (default: `30s`)
- `min_interval`: Minimum evaluation interval (default: `10s`)
- `max_attempts`: Retry attempts for failed evaluations (default: `3`)

High availability configuration:
- `ha_redis_address`: Redis server for HA clustering
- `ha_listen_address`: HA message listening address
- `ha_peers`: Initial cluster instances
- `ha_single_node_evaluation`: Single-instance rule evaluation mode

### `[log]`

- `mode`: `console`, `file`, or `syslog`
- `level`: `debug`, `info`, `warn`, `error`
- `filters`: Logger-specific levels (e.g., `sqlstore:debug`)

Sub-sections: `[log.console]`, `[log.file]`, `[log.syslog]`

### `[quota]`

Usage limits (set to `-1` for unlimited):

- `org_user`: Users per organization (default: `10`)
- `org_dashboard`: Dashboards per organization (default: `100`)
- `org_data_source`: Data sources per organization (default: `10`)
- `global_user`, `global_org`, `global_dashboard`: Global limits

### `[explore]`

- `enabled`: Enable Explore section
- `defaultTimeOffset`: Time offset from now (default: `1h`)

### `[metrics]`

- `enabled`: Enable metrics reporting (default: `true`)
- `interval_seconds`: Metrics flush interval (default: `10s`)

Sub-sections: `[metrics.graphite]` for Graphite integration

### `[tracing.opentelemetry]`

Distributed tracing configuration for observability.

## Configuration Priority

Environment variables override configuration file settings. After adding custom options, restart Grafana for changes to take effect.
