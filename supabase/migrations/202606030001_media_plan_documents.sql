alter table action_sheets
  add column if not exists document_markdown text,
  add column if not exists document_metadata jsonb,
  add column if not exists document_status text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'action_sheets_document_status_check'
  ) then
    alter table action_sheets
      add constraint action_sheets_document_status_check
      check (
        document_status is null
        or document_status in ('draft', 'pending', 'approved', 'rejected')
      );
  end if;
end
$$;
