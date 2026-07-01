"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_username', 'users', ['username'])

    # 2. domains table
    op.create_table(
        'domains',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_url', sa.String(length=2048), nullable=False),
        sa.Column('normalized_url', sa.String(length=2048), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('ssl_valid', sa.Boolean(), nullable=True),
        sa.Column('ssl_expires_at', sa.DateTime(), nullable=True),
        sa.Column('server_header', sa.String(length=255), nullable=True),
        sa.Column('robots_txt_url', sa.String(length=2048), nullable=True),
        sa.Column('robots_txt_content', sa.Text(), nullable=True),
        sa.Column('robots_txt_fetched_at', sa.DateTime(), nullable=True),
        sa.Column('robots_disallow', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('total_subdomains', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_sitemaps', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('crawled_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('first_crawl_at', sa.DateTime(), nullable=True),
        sa.Column('last_crawl_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('normalized_url')
    )
    op.create_index('idx_domains_user_id', 'domains', ['user_id'])
    op.create_index('idx_domains_domain', 'domains', ['domain'])
    op.create_index('idx_domains_status', 'domains', ['status'])
    op.create_index('idx_domains_last_crawl', 'domains', ['last_crawl_at'])

    # 3. subdomains table
    op.create_table(
        'subdomains',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subdomain', sa.String(length=255), nullable=False),
        sa.Column('normalized_url', sa.String(length=2048), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('total_sitemaps', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('crawled_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('health_score', sa.Integer(), server_default='100', nullable=False),
        sa.Column('crawled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('normalized_url')
    )
    op.create_index('idx_subdomains_domain_id', 'subdomains', ['domain_id'])
    op.create_index('idx_subdomains_subdomain', 'subdomains', ['subdomain'])
    op.create_index('idx_subdomains_status', 'subdomains', ['status'])

    # 4. sitemaps table
    op.create_table(
        'sitemaps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subdomain_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sitemap_url', sa.String(length=2048), nullable=False),
        sa.Column('is_index', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('parent_sitemap_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('discovered_from', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('url_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_modified', sa.Date(), nullable=True),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=True),
        sa.Column('parsed_at', sa.DateTime(), nullable=True),
        sa.Column('fetch_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_sitemap_id'], ['sitemaps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subdomain_id'], ['subdomains.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('sitemap_url')
    )
    op.create_index('idx_sitemaps_domain_id', 'sitemaps', ['domain_id'])
    op.create_index('idx_sitemaps_subdomain_id', 'sitemaps', ['subdomain_id'])
    op.create_index('idx_sitemaps_parent', 'sitemaps', ['parent_sitemap_id'])
    op.create_index('idx_sitemaps_status', 'sitemaps', ['status'])
    op.create_index('idx_sitemaps_is_index', 'sitemaps', ['is_index'])

    # 5. urls table
    op.create_table(
        'urls',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subdomain_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sitemap_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('url_hash', sa.String(length=64), nullable=False),
        sa.Column('sitemap_last_modified', sa.Date(), nullable=True),
        sa.Column('sitemap_change_frequency', sa.String(length=20), nullable=True),
        sa.Column('sitemap_priority', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('status_code', sa.SmallInteger(), nullable=True),
        sa.Column('status_category', sa.String(length=50), nullable=True),
        sa.Column('final_url', sa.String(length=2048), nullable=True),
        sa.Column('redirect_chain', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('content_length', sa.BigInteger(), nullable=True),
        sa.Column('canonical_url', sa.String(length=2048), nullable=True),
        sa.Column('robots_meta', sa.String(length=255), nullable=True),
        sa.Column('is_indexable', sa.Boolean(), nullable=True),
        sa.Column('crawl_status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('crawl_attempt', sa.Integer(), server_default='0', nullable=False),
        sa.Column('discovered_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sitemap_id'], ['sitemaps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subdomain_id'], ['subdomains.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('url_hash')
    )
    op.create_index('idx_urls_domain_id', 'urls', ['domain_id'])
    op.create_index('idx_urls_subdomain_id', 'urls', ['subdomain_id'])
    op.create_index('idx_urls_sitemap_id', 'urls', ['sitemap_id'])
    op.create_index('idx_urls_status_code', 'urls', ['status_code'])
    op.create_index('idx_urls_status_category', 'urls', ['status_category'])
    op.create_index('idx_urls_crawl_status', 'urls', ['crawl_status'])
    op.create_index('idx_urls_domain_status', 'urls', ['domain_id', 'status_category'])
    op.create_index('idx_urls_response_time', 'urls', ['response_time_ms'])
    op.create_index('idx_urls_last_checked', 'urls', ['last_checked_at'])

    # 6. crawl_jobs table
    op.create_table(
        'crawl_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('stage_domain_validation', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_dns_resolution', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_ssl_verification', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_robots_found', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_sitemap_discovery', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_parsing_indexes', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_parsing_sitemaps', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_url_discovery', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stage_http_checking', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('max_workers', sa.Integer(), server_default='32', nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), server_default='30', nullable=False),
        sa.Column('respect_robots_txt', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('follow_redirects', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('total_sitemaps_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_sitemaps_parsed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_urls_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_urls_checked', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_2xx', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_3xx', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_4xx', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_5xx', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_timeout', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_dns_error', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_ssl_error', sa.Integer(), server_default='0', nullable=False),
        sa.Column('avg_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('crawl_speed_urls_per_sec', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )
    op.create_index('idx_crawl_jobs_domain_id', 'crawl_jobs', ['domain_id'])
    op.create_index('idx_crawl_jobs_user_id', 'crawl_jobs', ['user_id'])
    op.create_index('idx_crawl_jobs_status', 'crawl_jobs', ['status'])
    op.create_index('idx_crawl_jobs_started', 'crawl_jobs', ['started_at'])

    # 7. crawl_logs table
    op.create_table(
        'crawl_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('crawl_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.String(length=255), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], ondelete='CASCADE')
    )
    op.create_index('idx_crawl_logs_crawl_job', 'crawl_logs', ['crawl_job_id', 'timestamp'])
    op.create_index('idx_crawl_logs_event_type', 'crawl_logs', ['event_type'])

    # 8. crawl_statistics table
    op.create_table(
        'crawl_statistics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('crawl_job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('total_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('successful_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('redirects', sa.Integer(), server_default='0', nullable=False),
        sa.Column('client_errors_4xx', sa.Integer(), server_default='0', nullable=False),
        sa.Column('server_errors_5xx', sa.Integer(), server_default='0', nullable=False),
        sa.Column('timeouts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('dns_errors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('ssl_errors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('network_errors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('avg_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('min_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('max_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('p95_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('p99_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('health_score', sa.Integer(), nullable=True),
        sa.Column('broken_links_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('redirect_chains_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('html_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('css_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('js_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('json_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('xml_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('image_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('pdf_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('video_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('other_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('crawl_start_time', sa.DateTime(), nullable=True),
        sa.Column('crawl_end_time', sa.DateTime(), nullable=True),
        sa.Column('crawl_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id']),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('domain_id')
    )
    op.create_index('idx_crawl_stats_domain', 'crawl_statistics', ['domain_id'])
    op.create_index('idx_crawl_stats_health', 'crawl_statistics', ['health_score'])

    # 9. reports table
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('crawl_job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('report_type', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('issues_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('generated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id']),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE')
    )
    op.create_index('idx_reports_domain', 'reports', ['domain_id'])
    op.create_index('idx_reports_type', 'reports', ['report_type'])

    # 10. crawl_history table
    op.create_table(
        'crawl_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('crawl_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_urls', sa.Integer(), nullable=True),
        sa.Column('successful_urls', sa.Integer(), nullable=True),
        sa.Column('broken_urls', sa.Integer(), nullable=True),
        sa.Column('redirects', sa.Integer(), nullable=True),
        sa.Column('avg_response_time_ms', sa.Integer(), nullable=True),
        sa.Column('health_score', sa.Integer(), nullable=True),
        sa.Column('crawled_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id']),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE')
    )
    op.create_index('idx_crawl_history_domain', 'crawl_history', ['domain_id', 'crawled_at'])

    # 11. crawl_comparison table
    op.create_table(
        'crawl_comparison',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('domain_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('previous_crawl_job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('current_crawl_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('urls_added', sa.Integer(), server_default='0', nullable=False),
        sa.Column('urls_removed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('new_broken_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('fixed_broken_urls', sa.Integer(), server_default='0', nullable=False),
        sa.Column('new_redirects', sa.Integer(), server_default='0', nullable=False),
        sa.Column('removed_redirects', sa.Integer(), server_default='0', nullable=False),
        sa.Column('health_score_change', sa.Integer(), server_default='0', nullable=False),
        sa.Column('compared_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['current_crawl_job_id'], ['crawl_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['previous_crawl_job_id'], ['crawl_jobs.id'], ondelete='SET NULL')
    )
    op.create_index('idx_crawl_comparison_domain', 'crawl_comparison', ['domain_id'])

    # 12. exports table
    op.create_table(
        'exports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('crawl_job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('export_type', sa.String(length=50), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('s3_key', sa.String(length=255), nullable=True),
        sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('download_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['crawl_job_id'], ['crawl_jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('idx_exports_user', 'exports', ['user_id'])
    op.create_index('idx_exports_created', 'exports', ['created_at'])

    # 13. sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=500), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )

    # 14. token_blocklist table
    op.create_table(
        'token_blocklist',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('token', sa.String(length=500), nullable=False),
        sa.Column('blacklisted_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('token')
    )
    op.create_index('idx_token_blocklist_token', 'token_blocklist', ['token'])


def downgrade() -> None:
    op.drop_table('token_blocklist')
    op.drop_table('sessions')
    op.drop_table('exports')
    op.drop_table('crawl_comparison')
    op.drop_table('crawl_history')
    op.drop_table('reports')
    op.drop_table('crawl_statistics')
    op.drop_table('crawl_logs')
    op.drop_table('crawl_jobs')
    op.drop_table('urls')
    op.drop_table('sitemaps')
    op.drop_table('subdomains')
    op.drop_table('domains')
    op.drop_table('users')
