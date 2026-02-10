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

# ------------------------
# Banco de Dados
# ------------------------
def load_db():
    if os.path.exists(DB):
        with open(DB, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "aprendizado" not in data: data["aprendizado"] = {}
            if "categorias" not in data or not data["categorias"]: 
                data["categorias"] = ["carnes", "hortifruti", "laticinios", "padaria", "outros"]
            return data
    return {
        "listas": {}, "historico": [], "aprendizado": {}, 
        "categorias": ["carnes", "hortifruti", "laticinios", "padaria", "outros"]
    }

def save_db(data):
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

db = load_db()

# ------------------------
# Funções Auxiliares
# ------------------------
def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def limpar_valor(texto):
    if not texto: return 0.0
    texto = texto.replace('.', '').replace(',', '.')
    match = re.search(r"\d+\.\d+", texto)
    return float(match.group()) if match else 0.0

def categorizar(nome):
    n = nome.lower()
    if n in db.get("aprendizado", {}): return db["aprendizado"][n]
    mapa = {
        "hortifruti": ["uva", "banana", "manga", "tomate", "papaia", "laranja"],
        "padaria": ["pao", "forma", "bisnaguinha"],
        "carnes": ["bovino", "frango", "acem", "alcatra", "peito", "sobrecoxa"],
        "laticinios": ["queijo", "leite", "mussarela", "muss", "iogurte", "creme leite"],
    }
    for cat, palavras in mapa.items():
        if any(p in n for p in palavras): return cat
    return "outros"

def extrair_nfce(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, timeout=15, headers=headers)
    if r.status_code != 200: raise Exception("Falha ao acessar NFC-e")
    soup = BeautifulSoup(r.text, "html.parser")
    loja = soup.find("div", class_="txtTopo")
    loja = loja.text.strip() if loja else "Supermercado"
    itens = []
    vistos = set()
    for tr in soup.select("tr[id^='Item +']"):
        nome_tag = tr.find(class_="txtTit")
        valor_total_tag = tr.find(class_="valor") 
        if nome_tag and valor_total_tag:
            nome = nome_tag.text.strip()
            valor_pago = limpar_valor(valor_total_tag.text)
            if valor_pago > 0 and nome not in vistos:
                vistos.add(nome)
                itens.append({"produto": nome, "valor": round(valor_pago, 2), "categoria": categorizar(nome), "marcado": False})
    return {"id": url, "loja": loja, "itens": itens, "mes": datetime.now().strftime("%Y-%m"), "data": datetime.now().strftime("%d/%m/%Y %H:%M")}

# ------------------------
# Interface Streamlit
# ------------------------
st.set_page_config(page_title="Compras Inteligentes", layout="wide")

with st.sidebar:
    st.title("🛒 Menu")
    menu = st.radio("Navegação", [
        "📸 Scan Cupom", "📋 Minhas Listas", "📊 Resumo Mensal", 
        "🗂️ Categorias", "📖 Histórico", "🔍 Onde é mais barato?"
    ])

# --- SCAN CUPOM ---
if menu == "📸 Scan Cupom":
    st.header("📸 Importar Cupom")
    if not db["listas"]:
        st.warning("Crie uma lista primeiro.")
    else:
        lista_dest = st.selectbox("Importar para:", list(db["listas"].keys()))
        t_foto, t_link = st.tabs(["📷 Foto", "🔗 Link"])
        
        with t_foto:
            img_file = st.file_uploader("Upload do QR Code", type=['png', 'jpg', 'jpeg'])
            if img_file:
                img = Image.open(img_file)
                dados = decode(img)
                if dados:
                    url_det = dados[0].data.decode()
                    if st.button("Confirmar e Importar Foto"):
                        if any(c.get("id") == url_det for c in db["historico"]):
                            st.error("Este cupom já foi importado!")
                        else:
                            compra = extrair_nfce(url_det)
                            db["listas"][lista_dest].extend(compra["itens"])
                            db["historico"].append(compra)
                            save_db(db)
                            st.success(f"✅ Cupom importado com sucesso: {compra['loja']}!")
                else:
                    st.error("QR Code não detectado.")

        with t_link:
            url_man = st.text_input("Cole o link aqui:")
            if st.button("Importar via Link") and url_man:
                if any(c.get("id") == url_man for c in db["historico"]):
                    st.error("Este cupom já foi importado!")
                else:
                    compra = extrair_nfce(url_man)
                    db["listas"][lista_dest].extend(compra["itens"])
                    db["historico"].append(compra)
                    save_db(db)
                    st.success(f"✅ Cupom importado com sucesso: {compra['loja']}!")

# --- MINHAS LISTAS ---
elif menu == "📋 Minhas Listas":
    st.header("📋 Minhas Listas")
    nome_l = st.text_input("Nova lista:")
    if st.button("Criar Lista") and nome_l:
        db["listas"][nome_l] = []; save_db(db); st.rerun()

    if db["listas"]:
        sel = st.selectbox("Lista ativa:", list(db["listas"].keys()))
        c_b1, c_b2, c_b3 = st.columns(3)
        if c_b1.button("✅ Marcar todos"):
            for i in range(len(db["listas"][sel])): db["listas"][sel][i]["marcado"] = True
            save_db(db); st.rerun()
        if c_b3.button("🗑️ Limpar marcados"):
            db["listas"][sel] = [i for i in db["listas"][sel] if not i["marcado"]]
            save_db(db); st.rerun()

        total = 0.0
        for i, item in enumerate(db["listas"][sel]):
            c1, c2, c3, c4 = st.columns([0.5, 3, 2, 1.5])
            marcado = c1.checkbox("", value=item["marcado"], key=f"it_{sel}_{i}")
            c2.write(item["produto"])
            idx_cat = db["categorias"].index(item["categoria"]) if item["categoria"] in db["categorias"] else 0
            n_cat = c3.selectbox("Cat", db["categorias"], index=idx_cat, key=f"ct_{sel}_{i}", label_visibility="collapsed")
            c4.write(f"R$ {item['valor']:.2f}")

            if marcado != item["marcado"] or n_cat != item["categoria"]:
                db["aprendizado"][item["produto"].lower()] = n_cat
                db["listas"][sel][i]["marcado"], db["listas"][sel][i]["categoria"] = marcado, n_cat
                save_db(db); st.rerun()
            if marcado: total += item["valor"]
        st.divider()
        st.subheader(f"Total Marcado: {formatar_moeda(total)}")

# --- RESUMO MENSAL ---
elif menu == "📊 Resumo Mensal":
    st.header("📊 Resumo Mensal")
    if not db["historico"]: st.info("Histórico vazio.")
    else:
        df = pd.DataFrame([{"mes": c["mes"], "produto": it["produto"].upper(), "cat": db.get("aprendizado", {}).get(it["produto"].lower(), it["categoria"]), "valor": it["valor"]} for c in db["historico"] for it in c["itens"]])
        mes_f = st.selectbox("Mês:", df["mes"].unique())
        df_m = df[df["mes"] == mes_f]
        st.bar_chart(df_m.groupby("cat")["valor"].sum())
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🏆 Top 5 Itens")
            top = df_m.groupby("produto")["valor"].sum().nlargest(5).reset_index()
            top.index = top.index + 1
            top["valor"] = top["valor"].apply(formatar_moeda)
            st.table(top.rename(columns={"produto": "Produto", "valor": "Total"}))
        with col2:
            st.subheader("💰 Resumo")
            st.metric("Total Gasto", formatar_moeda(df_m["valor"].sum()))

# --- CATEGORIAS ---
elif menu == "🗂️ Categorias":
    st.header("🗂️ Gerenciar Categorias")
    c1, c2 = st.columns([1, 1.5]) # Restaurado o layout de colunas
    with c1:
        st.subheader("➕ Adicionar")
        # Campo limpa automaticamente após adicionar
        nova_cat_input = st.text_input("Nome da categoria:", key="input_nova_cat")
        if st.button("Adicionar"):
            if nova_cat_input:
                cl = nova_cat_input.strip().lower()
                if cl not in db["categorias"]:
                    db["categorias"].append(cl)
                    save_db(db)
                    st.rerun() # Rerun garante que o campo de texto seja limpo
    with c2:
        st.subheader("🗑️ Atuais")
        for cat in db["categorias"]:
            cl1, cl2 = st.columns([3, 1])
            cl1.write(f"• {cat.capitalize()}")
            if len(db["categorias"]) > 1 and cl2.button("Remover", key=f"rem_{cat}"):
                db["categorias"].remove(cat)
                save_db(db)
                st.rerun()

# --- HISTÓRICO ---
elif menu == "📖 Histórico":
    st.header("📖 Histórico")
    for comp in reversed(db["historico"]):
        with st.expander(f"📅 {comp.get('data', 'S/D')} - {comp.get('loja', 'Loja')}"):
            df_h = pd.DataFrame(comp["itens"])
            df_h.index = df_h.index + 1
            st.table(df_h[["produto", "valor"]])
            st.write(f"**Total: {formatar_moeda(df_h['valor'].sum())}**")

# --- ONDE É MAIS BARATO? ---
elif menu == "🔍 Onde é mais barato?":
    st.header("🔍 Onde é mais barato?")
    if not db["historico"]: st.info("Sem dados.")
    else:
        dados = pd.DataFrame([{"Produto": it["produto"].upper(), "Loja": c["loja"], "Preço": it["valor"], "Data": c["data"]} for c in db["historico"] for it in c["itens"]])
        p_sel = st.selectbox("Produto:", sorted(dados["Produto"].unique()))
        if p_sel:
            df_p = dados[dados["Produto"] == p_sel].sort_values("Preço")
            st.success(f"✅ Melhor Preço: {formatar_moeda(df_p.iloc[0]['Preço'])} no {df_p.iloc[0]['Loja']}")
            df_p.index = range(1, len(df_p) + 1)
            df_p["Preço"] = df_p["Preço"].apply(formatar_moeda)
            st.dataframe(df_p[["Loja", "Preço", "Data"]], use_container_width=True)