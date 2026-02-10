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

# ==============================
# CSS — layout compacto mobile
# ==============================

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 1rem;}
div[data-testid="stVerticalBlock"] > div {gap: 0.5rem;}
.stCheckbox {margin-bottom: -10px;}
</style>
""", unsafe_allow_html=True)

# ==============================
# Banco
# ==============================

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

# ==============================
# Categoria automática
# ==============================

def categorizar(nome):
    n = nome.lower()

    mapa = {
        "hortifruti": ["uva","banana","manga","tomate","laranja","mamão"],
        "padaria": ["pao"],
        "carnes": ["bovino","frango","acem","alcatra"],
        "laticinios": ["leite","queijo","creme"]
    }

    for cat, palavras in mapa.items():
        if any(p in n for p in palavras):
            return cat

    return "outros"

# ==============================
# Scanner QR
# ==============================

def ler_qr(img):
    try:
        image = Image.open(img)
        d = decode(image)
        return d[0].data.decode() if d else None
    except:
        return None

# ==============================
# Limpeza valor
# ==============================

def limpar_valor(texto):
    if not texto:
        return 0
    match = re.search(r"\d+[,\.]\d+", texto)
    if match:
        return float(match.group().replace(",", "."))
    return 0

# ==============================
# Parser NFC-e
# ==============================

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

        # ignora totais
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

# ==============================
# UI
# ==============================

st.title("🛒 Compras Inteligentes")

menu = st.radio(
    "Menu",
    [
        "📸 Scan Cupom",
        "📋 Listas",
        "📊 Categorias",
        "📅 Resumo Mensal",
        "🗂 Histórico"
    ]
)

# ==============================
# SCAN CUPOM
# ==============================

if menu == "📸 Scan Cupom":

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

# ==============================
# LISTAS
# ==============================

elif menu == "📋 Listas":

    nova = st.text_input("Nova lista")

    if st.button("Criar"):
        db["listas"][nova] = []
        save_db(db)
        st.rerun()

    if db["listas"]:

        lista = st.selectbox("Escolha lista:", list(db["listas"].keys()))
        itens = db["listas"][lista]

        colA, colB = st.columns(2)

        if colA.button("Marcar todos"):
            for i in itens:
                i["marcado"] = True
            save_db(db)
            st.rerun()

        if colB.button("Desmarcar todos"):
            for i in itens:
                i["marcado"] = False
            save_db(db)
            st.rerun()

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

# ==============================
# CATEGORIAS
# ==============================

elif menu == "📊 Categorias":

    st.subheader("Gerenciar categorias")

    # junta todos os itens
    itens = []
    for c in db["historico"]:
        itens += c["itens"]

    if not itens:
        st.info("Sem compras registradas.")
        st.stop()

    df = pd.DataFrame(itens)

    categorias_existentes = sorted(df["categoria"].unique())

    st.markdown("### 📂 Categorias atuais")

    for cat in categorias_existentes:

        col1, col2 = st.columns([4,1])

        col1.write(cat)

        if col2.button("🗑", key=f"del_{cat}"):

            # move itens excluídos para "outros"
            for compra in db["historico"]:
                for item in compra["itens"]:
                    if item["categoria"] == cat:
                        item["categoria"] = "outros"

            save_db(db)
            st.rerun()

    st.divider()

    st.markdown("### ➕ Nova categoria")

    nova = st.text_input("Nome da categoria")

    if st.button("Criar categoria") and nova:

        for compra in db["historico"]:
            for item in compra["itens"]:
                if item["categoria"] == "outros":
                    item["categoria"] = nova

        save_db(db)
        st.success("Categoria criada!")
        st.rerun()

    st.divider()

    st.markdown("### 🔄 Reclassificar itens")

    item_sel = st.selectbox(
        "Escolha um item:",
        df["produto"].unique()
    )

    nova_cat = st.selectbox(
        "Mover para:",
        categorias_existentes + ["outros"]
    )

    if st.button("Atualizar categoria"):

        for compra in db["historico"]:
            for item in compra["itens"]:
                if item["produto"] == item_sel:
                    item["categoria"] = nova_cat

        save_db(db)
        st.success("Categoria atualizada!")
        st.rerun()

# ==============================
# RESUMO MENSAL
# ==============================

elif menu == "📅 Resumo Mensal":

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
        st.write("💰 Total do mês:", df["valor"].sum())

# ==============================
# HISTÓRICO
# ==============================

elif menu == "🗂 Histórico":

    for c in db["historico"][::-1]:

        with st.expander(f"{c['loja']} — {c['data']}"):
            st.dataframe(pd.DataFrame(c["itens"]))

