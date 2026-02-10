import streamlit as st
import requests
from bs4 import BeautifulSoup
import json, os
from datetime import datetime
from pyzbar.pyzbar import decode
from PIL import Image
import pandas as pd
import re

DB = "compras.json"

# ======================
# CSS compacto (mobile)
# ======================

st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.5rem;
}
.stCheckbox {
    margin-bottom: -10px;
}
</style>
""", unsafe_allow_html=True)

# ======================
# BANCO
# ======================

def load_db():
    if os.path.exists(DB):
        with open(DB, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return {"listas": {}, "historico": data}

        return data

    return {"listas": {}, "historico": []}


def save_db(data):
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


db = load_db()

# ======================
# CATEGORIA
# ======================

def categorizar(nome):

    n = nome.lower()

    mapa = {
        "hortifruti": ["uva", "banana", "manga", "tomate", "laranja", "mamão"],
        "padaria": ["pao"],
        "carnes": ["bovino", "frango", "acem"],
        "laticinios": ["leite", "queijo"],
    }

    for cat, palavras in mapa.items():
        if any(p in n for p in palavras):
            return cat

    return "outros"

# ======================
# QR scanner
# ======================

def ler_qr(img):
    try:
        image = Image.open(img)
        d = decode(image)
        return d[0].data.decode() if d else None
    except:
        return None

# ======================
# LIMPAR VALOR
# ======================

def limpar_valor(texto):

    if not texto:
        return 0

    match = re.search(r"\d+[,\.]\d+", texto)

    if match:
        return float(match.group().replace(",", "."))

    return 0

# ======================
# PARSER NFC-e
# ======================

def extrair_nfce(url):

    r = requests.get(url, timeout=15)

    if r.status_code != 200:
        raise Exception("Falha ao acessar NFC-e")

    soup = BeautifulSoup(r.text, "html.parser")

    loja = soup.find("div", class_="txtTopo")
    loja = loja.text.strip() if loja else "Loja"

    itens = []

    for item in soup.select(".txtTit"):

        nome = item.text.strip()
        nome_l = nome.lower()

        if "vl" in nome_l or "total" in nome_l:
            continue

        bloco = item.parent
        valor = bloco.find(class_="RvlUnit")

        itens.append({
            "produto": nome,
            "valor": limpar_valor(valor.text) if valor else 0,
            "categoria": categorizar(nome),
            "marcado": False
        })

    if not itens:
        raise Exception("Nenhum item encontrado")

    return {
        "id": hash(url),
        "data": datetime.now().isoformat(),
        "mes": datetime.now().strftime("%Y-%m"),
        "loja": loja,
        "itens": itens
    }

# ======================
# UI — MENU MOBILE
# ======================

st.title("🛒 Compras Inteligentes")

tabs = st.tabs([
    "📸 Scan Cupom",
    "📋 Minhas Listas",
    "📊 Resumo Mensal",
    "🗂 Histórico"
])

scan_tab, lista_tab, resumo_tab, hist_tab = tabs

# ======================
# SCAN CUPOM
# ======================

with scan_tab:

    if "qr_url" not in st.session_state:
        st.session_state.qr_url = None

    if not db["listas"]:

        nome = st.text_input("Crie sua primeira lista")

        if st.button("Criar lista"):
            db["listas"][nome] = []
            save_db(db)
            st.rerun()

    else:

        lista = st.selectbox("Importar para:", list(db["listas"].keys()))

        img = st.file_uploader("Fotografe o QR do cupom")

        if img:
            url = ler_qr(img)

            if url:
                st.session_state.qr_url = url
                st.success("QR detectado!")

        if st.session_state.qr_url:

            if st.button("Importar cupom"):

                try:

                    compra = extrair_nfce(st.session_state.qr_url)

                    if any(c.get("id") == compra["id"] for c in db["historico"]):
                        st.warning("Cupom já importado!")
                    else:
                        db["listas"][lista].extend(compra["itens"])
                        db["historico"].append(compra)
                        save_db(db)
                        st.success("Compra importada!")

                    st.session_state.qr_url = None
                    st.rerun()

                except Exception as e:
                    st.error(f"Erro: {e}")

# ======================
# LISTAS
# ======================

with lista_tab:

    nova = st.text_input("Nova lista")

    if st.button("Criar"):
        db["listas"][nova] = []
        save_db(db)
        st.rerun()

    if db["listas"]:

        lista = st.selectbox("Escolha lista:", list(db["listas"].keys()))
        itens = db["listas"][lista]

        total = 0

        for i, item in enumerate(itens):

            c1, c2, c3 = st.columns([1,5,2])

            marcado = c1.checkbox("", item["marcado"], key=f"{lista}{i}")
            db["listas"][lista][i]["marcado"] = marcado

            c2.write(item["produto"])
            c3.write(f"R$ {item['valor']:.2f}")

            if marcado:
                total += item["valor"]

        save_db(db)

        st.divider()
        st.subheader(f"💰 Total marcado: R$ {total:.2f}")

# ======================
# RESUMO
# ======================

with resumo_tab:

    if not db["historico"]:
        st.info("Sem compras.")
    else:

        meses = sorted({c["mes"] for c in db["historico"]})
        mes = st.selectbox("Mês:", meses)

        itens = []

        for c in db["historico"]:
            if c["mes"] == mes:
                itens += c["itens"]

        df = pd.DataFrame(itens)

        resumo = df.groupby("categoria")["valor"].sum()

        st.bar_chart(resumo)
        st.write("💰 Total:", df["valor"].sum())

# ======================
# HISTÓRICO
# ======================

with hist_tab:

    for c in db["historico"][::-1]:
        with st.expander(f"{c['loja']} — {c['data']}"):
            st.dataframe(pd.DataFrame(c["itens"]))
