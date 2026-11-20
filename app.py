"""
Checador de extremamente — versão online (Streamlit Cloud + Supadata)

Cole um link do YouTube -> busca a legenda em português (via Supadata)
-> lista cada "extremamente" com o tempo (HH:MM:SS) -> soma -> gera o texto.

Segredos necessários (Streamlit Cloud > Settings > Secrets, ou .streamlit/secrets.toml):
    SUPADATA_KEY = "sua-chave"
    SENHA = "uma-senha-simples"   # opcional, mas recomendada
"""

import hmac
import os
import re
import traceback
import unicodedata

import requests
import streamlit as st

PALAVRA = "extremamente"
CONTEXTO_PALAVRAS = 6  # quantas palavras mostrar antes/depois para você validar
API = "https://api.supadata.ai/v1/transcript"


class ErroLegenda(Exception):
    """Erro esperado, com mensagem pronta para mostrar ao usuário."""


def segredo(nome: str):
    try:
        return st.secrets[nome]
    except Exception:
        return os.environ.get(nome)


def normalizar(texto: str) -> str:
    """minúsculo, sem acento e sem pontuação: 'Extremamente,' -> 'extremamente'"""
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


def gerar_texto(total: int) -> str:
    vezes = "vez" if total == 1 else "vezes"
    return f"Checador de extremamente, esse vídeo usou {total} {vezes} a palavra extremamente."


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

url = st.text_input("Link do vídeo do YouTube")

if st.button("Checar", type="primary") and url.strip():
    video_id = extrair_id(url.strip())
    if not video_id:
        st.error("Não reconheci esse link do YouTube.")
        st.stop()

    titulo = titulo_video(video_id)
    if titulo:
        st.caption(f"Vídeo: {titulo}")

    try:
        with st.spinner("Buscando a legenda..."):
            palavras = buscar_legendas(video_id)
    except ErroLegenda as erro:
        st.warning(str(erro))
        st.stop()
    except Exception as erro:
        st.error(f"Não consegui processar esse link: {erro}")
        st.code(traceback.format_exc(), language=None)
        st.stop()

    ocorrencias = achar_ocorrencias(palavras)
    total = len(ocorrencias)

    st.subheader(f"Total: {total}")
    st.caption("Fonte: legendas do YouTube (via Supadata). O tempo é aproximado, por frase. Confira os links antes de postar.")
    st.code(gerar_texto(total), language=None)  # botão de copiar já vem no canto

    if ocorrencias:
        st.subheader("Onde apareceu (clique para validar no vídeo)")
        for inicio, contexto in ocorrencias:
            link = f"https://www.youtube.com/watch?v={video_id}&t={int(inicio)}s"
            st.markdown(f"**[{hhmmss(inicio)}]({link})** — …{contexto}…")
