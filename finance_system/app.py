import streamlit as st
import pandas as pd
from datetime import date
from src.database.connection import db_instance

# Configuração da Página deve ser a primeira linha executável
st.set_page_config(
    page_title="Finanças Modo Absoluto",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_summary():
    """Carrega estatísticas rápidas do banco."""
    conn = db_instance.get_connection()
    try:
        # Busca totais
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_recs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE category IS NULL OR category = ''")
        pending_recs = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(date), MAX(date) FROM transactions")
        min_date, max_date = cursor.fetchone()
        
        return total_recs, pending_recs, min_date, max_date
    except Exception as e:
        return 0, 0, None, None
    finally:
        conn.close()

# --- INTERFACE ---
st.title("🛡️ Finanças: Modo Absoluto")
st.markdown("### Visão Geral do Sistema")

# Carrega dados
total, pending, start, end = load_summary()

# Métricas de Topo
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Transações", total)

with col2:
    st.metric("Pendentes de Classificação", pending, delta_color="inverse")

with col3:
    if start:
        # Formatação de data pode variar conforme banco, tratamento básico
        st.metric("Início dos Registros", pd.to_datetime(start).strftime("%d/%m/%Y"))
    else:
        st.metric("Início", "-")

with col4:
    status = "Online" if total >= 0 else "Erro"
    st.metric("Status do Banco", status, delta="G: Drive Conectado" if "G:" in str(db_instance.db_path) else "Modo Local")

st.divider()

# Navegação Rápida (Atalhos)
st.subheader("🚀 Acesso Rápido")
c1, c2, c3 = st.columns(3)

with c1:
    with st.container(border=True):
        st.markdown("**📥 Ingestão de Dados**")
        st.caption("Importe extratos bancários (CSV) e faturas de cartão (TXT).")
        st.page_link("pages/1_📥_Extratos.py", label="Ir para Extratos", icon="📂")

with c2:
    with st.container(border=True):
        st.markdown("**📝 Passivos Futuros**")
        st.caption("Cadastre empréstimos e financiamentos manualmente.")
        st.page_link("pages/2_📝_Emprestimos.py", label="Gerir Empréstimos", icon="🏦")

with c3:
    with st.container(border=True):
        st.markdown("**🏷️ Classificação**")
        st.caption("Categorize despesas pendentes e crie regras.")
        # Nota: Criaremos esta página em breve
        st.page_link("pages/3_🏷️_Classificacao.py", label="Classificar", icon="🏷️")

# Rodapé Técnico
st.markdown("---")
st.caption(f"Caminho do Banco de Dados: `{db_instance.db_path}`")