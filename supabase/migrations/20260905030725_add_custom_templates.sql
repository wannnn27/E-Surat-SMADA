create table if not exists esurat.custom_templates (
    key text primary key check (key ~ '^[a-z][a-z0-9_]{2,49}$'),
    label text not null,
    description text not null,
    category text not null check (category in ('guru', 'murid')),
    default_code text not null,
    signer text not null check (signer in ('kepsek', 'pemohon', 'wali')),
    fields_json jsonb not null,
    filename text not null,
    content bytea not null,
    sha256 text not null,
    active boolean not null default true,
    created_at timestamptz not null default current_timestamp,
    updated_at timestamptz not null default current_timestamp,
    created_by text not null
);

alter table esurat.custom_templates enable row level security;
revoke all on table esurat.custom_templates from anon, authenticated, service_role;
grant select, insert, update, delete on table esurat.custom_templates to esurat_runtime;

drop policy if exists esurat_runtime_select_custom_templates on esurat.custom_templates;
create policy esurat_runtime_select_custom_templates
    on esurat.custom_templates
    for select
    to esurat_runtime
    using (true);

drop policy if exists esurat_runtime_insert_custom_templates on esurat.custom_templates;
create policy esurat_runtime_insert_custom_templates
    on esurat.custom_templates
    for insert
    to esurat_runtime
    with check (true);

drop policy if exists esurat_runtime_update_custom_templates on esurat.custom_templates;
create policy esurat_runtime_update_custom_templates
    on esurat.custom_templates
    for update
    to esurat_runtime
    using (true)
    with check (true);

drop policy if exists esurat_runtime_delete_custom_templates on esurat.custom_templates;
create policy esurat_runtime_delete_custom_templates
    on esurat.custom_templates
    for delete
    to esurat_runtime
    using (true);
