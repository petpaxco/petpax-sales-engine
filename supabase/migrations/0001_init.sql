-- PetPax Sales Engine — initial schema
-- One business record per salon from discovery through repeat orders.
-- Customers and prospects share the business table; stage tells them apart.

create extension if not exists pgcrypto;

create or replace function public.prefixed_id(prefix text)
returns text language sql volatile as $$
  select prefix || '_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16)
$$;

create or replace function public.touch_row()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  new.version := coalesce(old.version, 0) + 1;
  return new;
end $$;

-- ---------------------------------------------------------------- enums
create type business_type as enum ('salon','mobile','chain','boutique','daycare','vet','trainer','retail','distributor','individual','other');
create type pipeline_stage as enum (
  'new_lead','researching','qualified','approved_to_send','outreach_active','engaged',
  'meeting_requested','meeting_booked','meeting_completed','proposal_or_sample','negotiation','won',
  'active_account',
  'cold_call_required','call_attempted','nurture','dormant','lost','disqualified','unsubscribed','do_not_contact');
create type account_status as enum ('onboarding','active','at_risk','inactive');
create type email_status as enum ('unknown','valid','risky','invalid','bounced');
create type fact_kind as enum ('sourced','inference');
create type actor_kind as enum ('human','automation');

-- ------------------------------------------------------------ territory
create table territory (
  id text primary key default prefixed_id('ter'),
  name text not null unique,
  phase int not null,                 -- 1 SoCal, 2 rest of CA, 3 AZ/NV/OR/WA
  priority int not null default 100,  -- lower = sooner
  counties text[] not null default '{}',
  states text[] not null default '{}'
);

-- ------------------------------------------------------------- business
create table business (
  id text primary key default prefixed_id('biz'),
  name text not null,
  normalized_name text not null,
  type business_type not null default 'salon',
  is_mobile boolean not null default false,
  street text, city text, state text, zip text, country text default 'USA',
  lat double precision, lng double precision,
  territory_id text references territory(id),
  drive_minutes_from_base int,        -- from ZIP 90008, real road time when known
  place_id text unique,
  website text, website_domain text,
  phone text, phone_digits text,
  rating numeric(2,1), review_count int,
  locations_count int,
  social_links jsonb not null default '{}',
  maps_url text,
  source text not null,               -- google_places | website | retail_tracker | manual
  source_url text,
  source_ref text,                    -- e.g. tracker sheet + row
  discovered_at timestamptz not null default now(),
  verified_at timestamptz,
  merged_into text references business(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  updated_by text not null default 'system',
  version int not null default 1
);
create unique index business_domain_uq on business(website_domain) where website_domain is not null and merged_into is null;
create unique index business_phone_uq on business(phone_digits) where phone_digits is not null and merged_into is null;
create index business_norm_name_idx on business(normalized_name, zip);
create trigger business_touch before update on business for each row execute function touch_row();

create table contact (
  id text primary key default prefixed_id('con'),
  business_id text not null references business(id),
  name text, role text,
  email text, email_status email_status not null default 'unknown',
  phone text,
  is_decision_maker boolean not null default false,
  source_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  updated_by text not null default 'system',
  version int not null default 1
);
create unique index contact_email_uq on contact(lower(email)) where email is not null;
create trigger contact_touch before update on contact for each row execute function touch_row();

-- Every personalization claim must trace to a source or be labeled an inference.
create table enrichment_fact (
  id text primary key default prefixed_id('fct'),
  business_id text not null references business(id),
  fact text not null,
  kind fact_kind not null,
  source_url text,
  captured_at timestamptz not null default now(),
  model text,
  constraint sourced_needs_url check (kind = 'inference' or source_url is not null)
);

create table lead_score (
  business_id text primary key references business(id),
  total int not null check (total between 0 and 100),
  geo int not null, fit int not null, contact_quality int not null,
  personalization int not null, potential int not null,
  explanation jsonb not null,
  rules_version text not null,
  scored_at timestamptz not null default now()
);

-- ------------------------------------------------------------- pipeline
create table pipeline_state (
  business_id text primary key references business(id),
  stage pipeline_stage not null,
  entered_at timestamptz not null default now(),
  previous_stage pipeline_stage,
  next_action text,
  action_owner text,                  -- nathan | anthony | ...
  action_due date,
  set_by actor_kind not null default 'automation',
  updated_at timestamptz not null default now(),
  version int not null default 1
);
create trigger pipeline_touch before update on pipeline_state for each row execute function touch_row();

create table stage_history (
  id bigint generated always as identity primary key,
  business_id text not null references business(id),
  from_stage pipeline_stage, to_stage pipeline_stage not null,
  at timestamptz not null default now(),
  by text not null, reason text
);

-- Permanent. Never auto-cleared.
create table suppression (
  id bigint generated always as identity primary key,
  email text, domain text, business_id text references business(id),
  reason text not null check (reason in ('unsubscribe','bounce','complaint','do_not_contact','existing_customer','declined_future','legal')),
  source text not null,
  at timestamptz not null default now(),
  constraint one_target check (num_nonnulls(email, domain, business_id) >= 1)
);
create index suppression_email_idx on suppression(lower(email));
create index suppression_domain_idx on suppression(lower(domain));
create index suppression_business_idx on suppression(business_id);

-- ------------------------------------------------------------- outreach
create table template (
  id text primary key default prefixed_id('tpl'),
  name text not null, step int not null, product text,
  subject text not null, body text not null,
  status text not null default 'draft' check (status in ('draft','approved','retired')),
  approved_by text, approved_at timestamptz,
  created_at timestamptz not null default now()
);

create table campaign (
  id text primary key default prefixed_id('cmp'),
  name text not null, territory_id text references territory(id),
  sequence_days int[] not null default '{0,4,10,17}',
  daily_cap int not null default 20,
  status text not null default 'draft' check (status in ('draft','dry_run','live','paused','ended')),
  created_at timestamptz not null default now()
);

create table sequence_enrollment (
  id text primary key default prefixed_id('enr'),
  business_id text not null references business(id),
  contact_id text not null references contact(id),
  campaign_id text not null references campaign(id),
  step int not null default 0,
  next_send_at timestamptz,
  status text not null default 'active' check (status in ('active','paused','stopped','completed')),
  stop_reason text,
  created_at timestamptz not null default now()
);
create unique index one_active_enrollment on sequence_enrollment(business_id) where status = 'active';

create table message (
  id text primary key default prefixed_id('msg'),
  business_id text references business(id),
  contact_id text references contact(id),
  direction text not null check (direction in ('outbound','inbound')),
  mailbox text,
  gmail_message_id text unique, thread_id text,
  subject text, sent_at timestamptz,
  template_id text references template(id),
  generation_rationale jsonb,
  idempotency_key text unique,
  created_at timestamptz not null default now()
);

create table reply_classification (
  message_id text primary key references message(id),
  category text not null,
  confidence numeric(3,2) not null,
  model text, reviewed_by text, reviewed_at timestamptz
);

-- ---------------------------------------------------- tasks & meetings
create table task (
  id text primary key default prefixed_id('tsk'),
  business_id text references business(id),
  type text not null check (type in ('call','visit','email','onboarding','reorder','research','sample','review')),
  title text not null,
  owner text not null,
  due date,
  status text not null default 'open' check (status in ('open','done','skipped','snoozed')),
  outcome text, notes text,
  created_by text not null default 'system',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  version int not null default 1
);
create index task_open_idx on task(owner, due) where status = 'open';
create trigger task_touch before update on task for each row execute function touch_row();

create table call_log (
  id bigint generated always as identity primary key,
  task_id text references task(id),
  business_id text not null references business(id),
  outcome text not null check (outcome in ('no_answer','voicemail','spoke_employee','spoke_decision_maker','interested','requested_info','meeting_booked','not_interested','call_back_later','wrong_number','do_not_contact')),
  spoke_with text, notes text,
  at timestamptz not null default now(), by text not null
);

create table meeting (
  id text primary key default prefixed_id('mtg'),
  business_id text not null references business(id),
  type text not null check (type in ('phone','video','in_person')),
  calendar_event_id text unique,      -- only set after the Calendar API call succeeds
  starts_at timestamptz not null, ends_at timestamptz not null,
  status text not null default 'booked' check (status in ('booked','completed','cancelled','no_show')),
  created_at timestamptz not null default now()
);

create table meeting_note (
  id text primary key default prefixed_id('note'),
  business_id text references business(id),       -- null until matched
  source text not null, raw_ref text,
  extracted jsonb, match_confidence numeric(3,2),
  needs_review boolean not null default true,
  created_at timestamptz not null default now()
);

create table visit_plan (
  id text primary key default prefixed_id('vp'),
  plan_date date not null unique,
  status text not null default 'draft' check (status in ('draft','approved','done'))
);
create table visit_stop (
  id text primary key default prefixed_id('vs'),
  plan_id text not null references visit_plan(id),
  business_id text not null references business(id),
  stop_order int,
  eta time, drive_minutes int,
  status text not null default 'candidate' check (status in ('candidate','tentative','confirmed','done','skipped')),
  outcome text,
  unique (plan_id, business_id)
);

-- ------------------------------------------------- customers & orders
create table account (
  business_id text primary key references business(id),
  status account_status not null default 'active',
  owner text not null default 'anthony',
  products_carried text,
  first_order_at date, last_order_at date,
  last_order_value numeric(10,2),
  lifetime_revenue numeric(12,2),
  order_count int not null default 0,
  reorder_cycle_days int,
  next_reorder_estimate date,
  reorder_basis text,                 -- own_median | default_cycle | unknown
  next_follow_up date,
  last_interaction date,
  comm_preference text,
  notes text,
  growth_campaign_ok boolean not null default false,
  tracker_row_ref text,
  data_issues text[] not null default '{}',
  updated_at timestamptz not null default now(),
  version int not null default 1
);
create trigger account_touch before update on account for each row execute function touch_row();

create table "order" (
  id text primary key default prefixed_id('ord'),
  business_id text not null references business(id),
  order_date date,
  zenmelts_packs int, dentalmelts_packs int,
  total numeric(10,2),
  order_type text, channel text, paid boolean,
  shipped_at date,
  source_ref text unique,
  notes text
);

-- ------------------------------------------------- audit, config, cost
create table activity_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor text not null,
  business_id text references business(id),
  action text not null,
  details jsonb not null default '{}'
);
create rule activity_log_no_update as on update to activity_log do instead nothing;
create rule activity_log_no_delete as on delete to activity_log do instead nothing;

create table config (
  key text primary key, value jsonb not null,
  updated_at timestamptz not null default now(), updated_by text not null default 'system'
);

create table cost_ledger (
  day date not null, service text not null,
  units numeric not null default 0, usd numeric(10,4) not null default 0,
  primary key (day, service)
);

create table sync_state (
  sheet text not null, row_key text not null,
  last_pushed_version int, last_pulled_at timestamptz,
  primary key (sheet, row_key)
);

-- ------------------------------------------------ row level security
-- Jobs use the service role (bypasses RLS). No anon or authenticated access.
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- --------------------------------------------------------- seed config
insert into territory (name, phase, priority, counties, states) values
  ('LA County', 1, 10, '{Los Angeles}', '{CA}'),
  ('Orange County', 1, 20, '{Orange}', '{CA}'),
  ('Ventura County', 1, 30, '{Ventura}', '{CA}'),
  ('Inland Empire', 1, 40, '{Riverside,San Bernardino}', '{CA}'),
  ('San Diego County', 1, 50, '{San Diego}', '{CA}'),
  ('Rest of California', 2, 100, '{}', '{CA}'),
  ('Regional expansion', 3, 200, '{}', '{AZ,NV,OR,WA}');
