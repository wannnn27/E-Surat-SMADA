-- Role runtime Vercel: hak minimum, tanpa DDL dan tanpa akses Data API.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'esurat_runtime') then
        create role esurat_runtime
            nologin
            nosuperuser
            nocreatedb
            nocreaterole
            noinherit
            noreplication
            nobypassrls;
    end if;
end
$$;

grant connect on database postgres to esurat_runtime;
grant usage on schema esurat to esurat_runtime;
grant select on table esurat.master_data to esurat_runtime;
grant select, insert, update on table
    esurat.riwayat_surat,
    esurat.nomor_counter
to esurat_runtime;
grant usage, select on all sequences in schema esurat to esurat_runtime;

drop policy if exists esurat_runtime_select_master on esurat.master_data;
create policy esurat_runtime_select_master
    on esurat.master_data
    for select
    to esurat_runtime
    using (true);

drop policy if exists esurat_runtime_select_history on esurat.riwayat_surat;
create policy esurat_runtime_select_history
    on esurat.riwayat_surat
    for select
    to esurat_runtime
    using (true);

drop policy if exists esurat_runtime_insert_history on esurat.riwayat_surat;
create policy esurat_runtime_insert_history
    on esurat.riwayat_surat
    for insert
    to esurat_runtime
    with check (true);

drop policy if exists esurat_runtime_update_history on esurat.riwayat_surat;
create policy esurat_runtime_update_history
    on esurat.riwayat_surat
    for update
    to esurat_runtime
    using (true)
    with check (true);

drop policy if exists esurat_runtime_select_counter on esurat.nomor_counter;
create policy esurat_runtime_select_counter
    on esurat.nomor_counter
    for select
    to esurat_runtime
    using (true);

drop policy if exists esurat_runtime_insert_counter on esurat.nomor_counter;
create policy esurat_runtime_insert_counter
    on esurat.nomor_counter
    for insert
    to esurat_runtime
    with check (true);

drop policy if exists esurat_runtime_update_counter on esurat.nomor_counter;
create policy esurat_runtime_update_counter
    on esurat.nomor_counter
    for update
    to esurat_runtime
    using (true)
    with check (true);
