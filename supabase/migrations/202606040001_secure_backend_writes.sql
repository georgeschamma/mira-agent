create schema if not exists private;

revoke all on schema private from public;
grant usage on schema private to authenticated, service_role;

create or replace function private.org_role(target_org uuid)
returns text
language sql
stable
security definer
set search_path = public
as $$
  select role
  from organization_members
  where org_id = target_org and user_id = auth.uid()
$$;

create or replace function private.campaign_org(target_campaign uuid)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select org_id from campaigns where id = target_campaign
$$;

create or replace function private.action_sheet_org(target_sheet uuid)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select c.org_id
  from action_sheets s
  join campaigns c on c.id = s.campaign_id
  where s.id = target_sheet
$$;

revoke all on function private.org_role(uuid) from public;
revoke all on function private.campaign_org(uuid) from public;
revoke all on function private.action_sheet_org(uuid) from public;
grant execute on function private.org_role(uuid) to authenticated, service_role;
grant execute on function private.campaign_org(uuid) to authenticated, service_role;
grant execute on function private.action_sheet_org(uuid) to authenticated, service_role;

drop policy if exists "read own orgs" on organizations;
drop policy if exists "read org memberships" on organization_members;
drop policy if exists "read org campaigns" on campaigns;
drop policy if exists "read org runs" on campaign_runs;
drop policy if exists "read org sheets" on action_sheets;
drop policy if exists "read org approvals" on action_sheet_approvals;
drop policy if exists "read org audit" on audit_log;

create policy "read own orgs"
  on organizations for select
  to authenticated
  using ((select private.org_role(id)) is not null);

create policy "read org memberships"
  on organization_members for select
  to authenticated
  using ((select private.org_role(org_id)) is not null);

create policy "read org campaigns"
  on campaigns for select
  to authenticated
  using ((select private.org_role(org_id)) is not null);

create policy "read org runs"
  on campaign_runs for select
  to authenticated
  using ((select private.org_role(private.campaign_org(campaign_id))) is not null);

create policy "read org sheets"
  on action_sheets for select
  to authenticated
  using ((select private.org_role(private.campaign_org(campaign_id))) is not null);

create policy "read org approvals"
  on action_sheet_approvals for select
  to authenticated
  using ((select private.org_role(private.action_sheet_org(action_sheet_id))) is not null);

create policy "read org audit"
  on audit_log for select
  to authenticated
  using ((select private.org_role(private.campaign_org(campaign_id))) is not null);

drop policy if exists "insert own orgs" on organizations;
drop policy if exists "insert org campaigns" on campaigns;
drop policy if exists "update org campaigns" on campaigns;
drop policy if exists "insert org runs" on campaign_runs;
drop policy if exists "update org runs" on campaign_runs;
drop policy if exists "insert org sheets" on action_sheets;
drop policy if exists "insert org approvals" on action_sheet_approvals;
drop policy if exists "admin update org approvals" on action_sheet_approvals;
drop policy if exists "insert org audit" on audit_log;

revoke insert, update, delete on table organizations from anon, authenticated;
revoke insert, update, delete on table organization_members from anon, authenticated;
revoke insert, update, delete on table campaigns from anon, authenticated;
revoke insert, update, delete on table campaign_runs from anon, authenticated;
revoke insert, update, delete on table action_sheets from anon, authenticated;
revoke insert, update, delete on table action_sheet_approvals from anon, authenticated;
revoke insert, update, delete on table audit_log from anon, authenticated;

drop function if exists public.action_sheet_org(uuid);
drop function if exists public.campaign_org(uuid);
drop function if exists public.org_role(uuid);

create or replace function public.update_action_sheet_approval(
  target_action_sheet_id uuid,
  target_recommendation_id text,
  target_status text,
  target_approved_by uuid,
  target_approved_at timestamptz
)
returns table (
  action_sheet_id uuid,
  recommendation_id text,
  status text
)
language sql
security invoker
set search_path = public
as $$
  with updated_approval as (
    update action_sheet_approvals
    set
      status = target_status,
      approved_by = target_approved_by,
      approved_at = target_approved_at
    where action_sheet_id = target_action_sheet_id
      and recommendation_id = target_recommendation_id
    returning action_sheet_id, recommendation_id, status
  ),
  updated_sheet as (
    update action_sheets
    set document_status = target_status
    where id = target_action_sheet_id
      and target_recommendation_id = 'document'
      and exists (select 1 from updated_approval)
  )
  select action_sheet_id, recommendation_id, status
  from updated_approval
$$;

revoke all on function public.update_action_sheet_approval(uuid, text, text, uuid, timestamptz)
  from public, anon, authenticated;
grant execute on function public.update_action_sheet_approval(uuid, text, text, uuid, timestamptz)
  to service_role;
