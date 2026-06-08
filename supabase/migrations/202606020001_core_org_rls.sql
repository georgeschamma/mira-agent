create extension if not exists pgcrypto;

create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  created_at timestamptz default now()
);

create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_by uuid references auth.users(id) not null,
  created_at timestamptz default now()
);

create table organization_members (
  org_id uuid references organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete cascade,
  role text not null check (role in ('analyst', 'admin')),
  created_at timestamptz default now(),
  primary key (org_id, user_id)
);

create table campaigns (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references organizations(id) not null,
  created_by uuid references auth.users(id) not null,
  brief jsonb not null,
  latest_run_id uuid,
  created_at timestamptz default now()
);

create table campaign_runs (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references campaigns(id) on delete cascade not null,
  status text default 'running' check (status in ('running', 'done', 'partial', 'error')),
  started_at timestamptz default now(),
  completed_at timestamptz,
  error text
);

alter table campaigns
  add constraint campaigns_latest_run_fk
  foreign key (latest_run_id) references campaign_runs(id);

create table action_sheets (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references campaigns(id) on delete cascade not null,
  run_id uuid references campaign_runs(id) on delete cascade not null,
  recommendations jsonb not null,
  model_used text not null,
  processing_ms integer,
  created_at timestamptz default now()
);

create table action_sheet_approvals (
  id uuid primary key default gen_random_uuid(),
  action_sheet_id uuid references action_sheets(id) on delete cascade not null,
  recommendation_id text not null,
  status text default 'pending' check (status in ('pending', 'approved', 'rejected')),
  approved_by uuid references auth.users(id),
  approved_at timestamptz,
  created_at timestamptz default now(),
  unique (action_sheet_id, recommendation_id)
);

create table audit_log (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references campaigns(id) on delete cascade not null,
  run_id uuid references campaign_runs(id) on delete cascade not null,
  step_index integer not null,
  node text not null,
  summary text not null,
  source text,
  confidence text check (confidence in ('high', 'medium', 'low')),
  pii_accessed boolean default false,
  model_used text,
  created_at timestamptz default now(),
  unique (run_id, step_index, node)
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

create or replace function public.org_role(target_org uuid)
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

create or replace function public.campaign_org(target_campaign uuid)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select org_id from campaigns where id = target_campaign
$$;

create or replace function public.action_sheet_org(target_sheet uuid)
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

alter table profiles enable row level security;
alter table organizations enable row level security;
alter table organization_members enable row level security;
alter table campaigns enable row level security;
alter table campaign_runs enable row level security;
alter table action_sheets enable row level security;
alter table action_sheet_approvals enable row level security;
alter table audit_log enable row level security;

create policy "read own profile"
  on profiles for select
  using (id = auth.uid());

create policy "read own orgs"
  on organizations for select
  using (org_role(id) is not null);

create policy "insert own orgs"
  on organizations for insert
  with check (created_by = auth.uid());

create policy "read org memberships"
  on organization_members for select
  using (org_role(org_id) is not null);

create policy "read org campaigns"
  on campaigns for select
  using (org_role(org_id) is not null);

create policy "insert org campaigns"
  on campaigns for insert
  with check (created_by = auth.uid() and org_role(org_id) in ('analyst', 'admin'));

create policy "update org campaigns"
  on campaigns for update
  using (org_role(org_id) in ('analyst', 'admin'))
  with check (org_role(org_id) in ('analyst', 'admin'));

create policy "read org runs"
  on campaign_runs for select
  using (org_role(campaign_org(campaign_id)) is not null);

create policy "insert org runs"
  on campaign_runs for insert
  with check (org_role(campaign_org(campaign_id)) in ('analyst', 'admin'));

create policy "update org runs"
  on campaign_runs for update
  using (org_role(campaign_org(campaign_id)) in ('analyst', 'admin'))
  with check (org_role(campaign_org(campaign_id)) in ('analyst', 'admin'));

create policy "read org sheets"
  on action_sheets for select
  using (org_role(campaign_org(campaign_id)) is not null);

create policy "insert org sheets"
  on action_sheets for insert
  with check (org_role(campaign_org(campaign_id)) in ('analyst', 'admin'));

create policy "read org approvals"
  on action_sheet_approvals for select
  using (org_role(action_sheet_org(action_sheet_id)) is not null);

create policy "insert org approvals"
  on action_sheet_approvals for insert
  with check (org_role(action_sheet_org(action_sheet_id)) in ('analyst', 'admin'));

create policy "admin update org approvals"
  on action_sheet_approvals for update
  using (org_role(action_sheet_org(action_sheet_id)) = 'admin')
  with check (org_role(action_sheet_org(action_sheet_id)) = 'admin');

create policy "read org audit"
  on audit_log for select
  using (org_role(campaign_org(campaign_id)) is not null);

create policy "insert org audit"
  on audit_log for insert
  with check (org_role(campaign_org(campaign_id)) in ('analyst', 'admin'));

