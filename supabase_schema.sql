-- Tabela de histórico de checagens (Supabase / PostgreSQL)
create table if not exists public.checagens (
  id bigint generated always as identity primary key,
  video_id text not null,
  titulo text,
  checado_em timestamptz not null default now()
);

-- Índice composto para buscar rapidamente a última checagem por video_id
create index if not exists idx_checagens_video_data
  on public.checagens (video_id, checado_em desc);

-- Índice para consultas do histórico por período
create index if not exists idx_checagens_data
  on public.checagens (checado_em desc);

-- Ativa Row Level Security (RLS)
alter table public.checagens enable row level security;

-- Permissão explícita de leitura (SELECT) para a chave pública (anon)
create policy "Permitir leitura de checagens"
  on public.checagens
  for select
  to anon
  using (true);

-- Permissão explícita de inserção (INSERT) para a chave pública (anon)
create policy "Permitir insercao de checagens"
  on public.checagens
  for insert
  to anon
  with check (char_length(video_id) = 11);
