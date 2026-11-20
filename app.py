"""
Checador de extremamente — versão online (Streamlit Cloud + Supadata + Supabase)

Cole um link do YouTube -> consulta histórico no Supabase (horário de Brasília)
-> busca a legenda em português (via Supadata) -> lista cada "extremamente"
com o tempo (HH:MM:SS) -> soma -> gera o texto -> grava sucesso no histórico.

Segredos necessários (Streamlit Cloud > Settings > Secrets, ou .streamlit/secrets.toml):
    SUPADATA_KEY = "sua-chave"
    SENHA = "uma-senha-simples"            # opcional, mas recomendada
    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_KEY = "sua-chave-anon-ou-publishable"
"""

from datetime import datetime, time, timedelta
import hmac
import os
import re
import traceback
import unicodedata
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

PALAVRA = "extremamente"
CONTEXTO_PALAVRAS = 6  # quantas palavras mostrar antes/depois para você validar
API = "https://api.supadata.ai/v1/transcript"
TZ_BR = ZoneInfo("America/Sao_Paulo")


class ErroLegenda(Exception):
    """Erro esperado, com mensagem pronta para mostrar ao usuário."""


def segredo(nome: str):
    try:
        val = st.secrets[nome]
        return val if val != "" else None
    except Exception:
        val = os.environ.get(nome)
        return val if val else None


def normalizar(texto: str) -> str:
    """Minúsculo, sem acento e sem pontuação: 'Extremamente,' -> 'extremamente'."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", texto)


def hhmmss(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def extrair_id(url: str):
    achou = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", url)
    if achou:
        return achou.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    return None


def titulo_video(video_id: str) -> str:
    """Só para você confirmar que é o vídeo certo. Se falhar, segue sem título."""
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=5,
        )
        return r.json().get("title", "") if r.ok else ""
    except Exception:
        return ""


def parse_iso_br(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TZ_BR)


# ---------------- Integração Supabase (REST API via requests) ----------------
def supabase_configurado() -> bool:
    return bool(segredo("SUPABASE_URL") and segredo("SUPABASE_KEY"))


def _supabase_headers() -> dict:
    chave = segredo("SUPABASE_KEY")
    return {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }


def _supabase_rest_url() -> str:
    base = str(segredo("SUPABASE_URL")).rstrip("/")
    return f"{base}/rest/v1/checagens"


def consultar_ultima_checagem(video_id: str) -> tuple[datetime | None, str | None]:
    """
    Retorna (data_hora_brasilia, aviso_erro_banco).
    Se não houver registro, retorna (None, None).
    Se falhar a conexão/API, retorna (None, mensagem_aviso).
    """
    if not supabase_configurado():
        return None, None

    try:
        resp = requests.get(
            _supabase_rest_url(),
            headers=_supabase_headers(),
            params={
                "select": "checado_em",
                "video_id": f"eq.{video_id}",
                "order": "checado_em.desc",
                "limit": "1",
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return None, f"Histórico indisponível no momento (erro {resp.status_code}). A checagem segue normalmente."
        linhas = resp.json()
        if not linhas:
            return None, None
        return parse_iso_br(linhas[0]["checado_em"]), None
    except Exception:
        return None, "Histórico indisponível no momento. A checagem segue normalmente."


def registrar_checagem(video_id: str, titulo: str) -> str | None:
    """
    Grava checagem bem-sucedida no Supabase.
    Retorna None se gravou ok, ou mensagem de aviso se falhou.
    """
    if not supabase_configurado():
        return None

    payload = {
        "video_id": video_id,
        "titulo": titulo.strip() if titulo and titulo.strip() else None,
    }
    try:
        headers = _supabase_headers()
        headers["Prefer"] = "return=minimal"
        resp = requests.post(
            _supabase_rest_url(),
            headers=headers,
            json=payload,
            timeout=8,
        )
        if resp.status_code not in (200, 201, 204):
            return f"Não foi possível salvar no histórico (erro {resp.status_code})."
        return None
    except Exception:
        return "Não foi possível salvar no histórico no momento."


def buscar_historico_periodo(data_inicio: datetime, data_fim: datetime) -> tuple[list[dict], str | None]:
    """
    Busca registros entre data_inicio e data_fim (já convertidos para UTC na consulta),
    ordenados do mais recente para o mais antigo.
    """
    if not supabase_configurado():
        return [], "Configure SUPABASE_URL e SUPABASE_KEY nos Secrets para usar o histórico."

    ini_utc = data_inicio.astimezone(ZoneInfo("UTC")).isoformat()
    fim_utc = data_fim.astimezone(ZoneInfo("UTC")).isoformat()

    try:
        resp = requests.get(
            _supabase_rest_url(),
            headers=_supabase_headers(),
            params=[
                ("select", "id,video_id,titulo,checado_em"),
                ("checado_em", f"gte.{ini_utc}"),
                ("checado_em", f"lte.{fim_utc}"),
                ("order", "checado_em.desc"),
            ],
            timeout=10,
        )
        if resp.status_code != 200:
            return [], f"Histórico indisponível no momento (erro {resp.status_code})."
        return resp.json(), None
    except Exception:
        return [], "Histórico indisponível no momento."


# ---------------- Legenda e análise ----------------
@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)  # mesmo vídeo no mesmo dia = não gasta crédito
def buscar_legendas(video_id: str):
    """Retorna lista de (palavra, início_em_segundos). Só aceita legenda em português."""
    resp = requests.get(
        API,
        params={
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "lang": "pt",
            "text": "false",
            "mode": "native",  # só legenda que já existe (1 crédito); nunca gera por IA (gasta mais)
        },
        headers={"x-api-key": segredo("SUPADATA_KEY")},
        timeout=60,
    )

    if resp.status_code in (401, 403):
        raise ErroLegenda("A chave do Supadata não foi aceita. Confira o SUPADATA_KEY.")
    if resp.status_code == 402:
        raise ErroLegenda("Os créditos gratuitos deste mês acabaram. Eles voltam no mês que vem.")
    if resp.status_code == 429:
        raise ErroLegenda("Muitas consultas seguidas. Espere alguns segundos e tente de novo.")
    if resp.status_code in (206, 404):
        raise ErroLegenda("Esse vídeo não tem legenda disponível, então não dá para checar online.")
    if resp.status_code != 200:
        raise ErroLegenda(f"O Supadata respondeu com erro {resp.status_code}: {resp.text[:200]}")

    dados = resp.json()
    idioma = str(dados.get("lang", ""))
    if not idioma.lower().startswith("pt"):
        disponiveis = ", ".join(dados.get("availableLangs", [])) or idioma or "nenhum"
        raise ErroLegenda(f"Esse vídeo não tem legenda em português (idiomas disponíveis: {disponiveis}).")

    conteudo = dados.get("content", [])
    palavras = []
    if isinstance(conteudo, list):
        for trecho in conteudo:
            for palavra in trecho["text"].replace("\n", " ").split():
                palavras.append((palavra, trecho["offset"] / 1000))  # offset vem em milissegundos
    if not palavras:
        raise ErroLegenda("A legenda veio vazia.")
    return palavras


def achar_ocorrencias(palavras):
    ocorrencias = []
    for i, (palavra, inicio) in enumerate(palavras):
        if normalizar(palavra) == PALAVRA:
            ini = max(0, i - CONTEXTO_PALAVRAS)
            fim = min(len(palavras), i + CONTEXTO_PALAVRAS + 1)
            contexto = " ".join(p for p, _ in palavras[ini:fim])
            ocorrencias.append((inicio, contexto))
    return ocorrencias


def gerar_texto(tempos) -> str:
    """
    Comentário pronto para o YouTube, em UMA linha só (o YouTube não reconhece
    quebras de linha): contagem + horários + provocação.
    """
    total = len(tempos)
    if total == 0:
        return "Checador de extremamente: essa palavra não apareceu neste vídeo."

    horarios = ", ".join(hhmmss(t) for t in tempos)
    if total == 1:
        contagem = "essa palavra apareceu 1 vez neste vídeo."
        pergunta = "ela foi bem usada nessa única vez ou você trocaria por outra?"
    else:
        contagem = f"essa palavra apareceu {total} vezes neste vídeo."
        pergunta = f"ela foi bem usada em todas as {total} vezes ou você trocaria alguma?"

    return f"Checador de extremamente: {contagem} {horarios} Conta aí, de forma leve e respeitosa: {pergunta}"


def executar_checagem(video_id: str) -> dict:
    """Executa a checagem completa, grava no Supabase se der certo e retorna o pacote de resultado."""
    titulo = titulo_video(video_id)
    palavras = buscar_legendas(video_id)
    ocorrencias = achar_ocorrencias(palavras)
    aviso_gravacao = registrar_checagem(video_id, titulo)
    return {
        "video_id": video_id,
        "titulo": titulo,
        "ocorrencias": ocorrencias,
        "aviso_gravacao": aviso_gravacao,
    }


def renderizar_resultado(res: dict):
    ocorrencias = res["ocorrencias"]
    total = len(ocorrencias)
    video_id = res["video_id"]
    titulo = res.get("titulo", "")

    if titulo:
        st.caption(f"Vídeo: {titulo}")
    if res.get("aviso_gravacao"):
        st.caption(f"⚠️ {res['aviso_gravacao']}")

    st.subheader(f"Total: {total}")
    st.caption("Fonte: legendas do YouTube (via Supadata). O tempo é aproximado, por frase. Confira os links antes de postar.")
    st.code(gerar_texto([inicio for inicio, _ in ocorrencias]), language=None, wrap_lines=True)

    st.subheader("Onde apareceu (clique para validar no vídeo)")
    if not ocorrencias:
        st.write("Nenhuma ocorrência encontrada.")
    for inicio, contexto in ocorrencias:
        link = f"https://www.youtube.com/watch?v={video_id}&t={int(inicio)}s"
        st.markdown(f"**[{hhmmss(inicio)}]({link})** — …{contexto}…")


# ---------------- Interface ----------------
st.set_page_config(page_title="Checador de extremamente", page_icon="🔎")
st.title("🔎 Checador de extremamente")

# Senha (evita que outras pessoas gastem seus créditos gratuitos)
senha = segredo("SENHA")
if senha:
    digitada = st.text_input("Senha", type="password")
    if not hmac.compare_digest(str(digitada), str(senha)):
        st.stop()

if not segredo("SUPADATA_KEY"):
    st.error("Falta configurar a chave SUPADATA_KEY nos Secrets do app.")
    st.stop()

# Estado da sessão para evitar regravação acidental e manter resultado visível
if "pendente_repetido" not in st.session_state:
    st.session_state.pendente_repetido = None  # dict com {"video_id": ..., "ultima_dt": ...}
if "ultimo_resultado" not in st.session_state:
    st.session_state.ultimo_resultado = None

aba_checar, aba_historico = st.tabs(["Checar vídeo", "Histórico"])

with aba_checar:
    url = st.text_input("Link do vídeo do YouTube", key="campo_url_youtube")

    if st.button("Checar", type="primary"):
        st.session_state.ultimo_resultado = None
        st.session_state.pendente_repetido = None

        if not url.strip():
            st.warning("Cole ou digite um link do YouTube antes de checar.")
            st.stop()

        video_id = extrair_id(url.strip())
        if not video_id:
            st.error("Não reconheci esse link do YouTube.")
            st.stop()

        ultima_dt, aviso_banco = consultar_ultima_checagem(video_id)
        if aviso_banco:
            st.caption(f"⚠️ {aviso_banco}")

        if ultima_dt is not None:
            st.session_state.pendente_repetido = {
                "video_id": video_id,
                "ultima_dt": ultima_dt,
            }
        else:
            try:
                with st.spinner("Buscando a legenda..."):
                    st.session_state.ultimo_resultado = executar_checagem(video_id)
            except ErroLegenda as erro:
                st.warning(str(erro))
            except Exception as erro:
                st.error(f"Não consegui processar esse link: {erro}")
                st.code(traceback.format_exc(), language=None)

    # Aviso de vídeo já checado (apenas data/hora em Brasília + botão "Checar mesmo assim")
    pendente = st.session_state.pendente_repetido
    if pendente is not None:
        formatada = pendente["ultima_dt"].strftime("%d/%m/%Y às %H:%M")
        st.info(f"Este vídeo já foi checado em **{formatada}** (horário de Brasília).")

        if st.button("Checar mesmo assim"):
            vid = pendente["video_id"]
            st.session_state.pendente_repetido = None
            try:
                with st.spinner("Buscando a legenda..."):
                    st.session_state.ultimo_resultado = executar_checagem(vid)
            except ErroLegenda as erro:
                st.warning(str(erro))
            except Exception as erro:
                st.error(f"Não consegui processar esse link: {erro}")
                st.code(traceback.format_exc(), language=None)

    if st.session_state.ultimo_resultado is not None:
        renderizar_resultado(st.session_state.ultimo_resultado)

with aba_historico:
    hoje_br = datetime.now(TZ_BR).date()
    padrao_inicio = hoje_br - timedelta(days=30)

    col1, col2 = st.columns(2)
    with col1:
        data_ini = st.date_input("Data inicial", value=padrao_inicio, format="DD/MM/YYYY")
    with col2:
        data_fim = st.date_input("Data final", value=hoje_br, format="DD/MM/YYYY")

    if data_ini > data_fim:
        st.warning("A data inicial não pode ser maior que a data final.")
    else:
        dt_ini_br = datetime.combine(data_ini, time.min, tzinfo=TZ_BR)
        dt_fim_br = datetime.combine(data_fim, time.max, tzinfo=TZ_BR)

        registros, erro_hist = buscar_historico_periodo(dt_ini_br, dt_fim_br)
        if erro_hist:
            st.warning(erro_hist)
        elif not registros:
            st.info("Nenhuma checagem encontrada no período selecionado.")
        else:
            linhas_tabela = []
            for item in registros:
                vid = item.get("video_id", "")
                dt_br = parse_iso_br(item["checado_em"]).strftime("%d/%m/%Y %H:%M")
                titulo_limpo = (item.get("titulo") or "").strip()
                rotulo_link = titulo_limpo if titulo_limpo else vid
                link_youtube = f"https://www.youtube.com/watch?v={vid}"
                linhas_tabela.append(
                    {
                        "Data (Brasília)": dt_br,
                        "Vídeo": rotulo_link,
                        "Link": link_youtube,
                    }
                )

            df = pd.DataFrame(linhas_tabela)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="Abrir no YouTube"),
                },
            )
