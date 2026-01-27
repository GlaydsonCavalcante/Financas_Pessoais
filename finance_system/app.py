import streamlit as st
import pandas as pd
from src.controllers.importer import ImportController
from src.database import DatabaseManager

st.set_page_config(page_title="Finanças Absolutas", layout="wide")

st.title("📡 Ingestão de Dados")
st.markdown("---")

# 1. Upload Area
uploaded_files = st.file_uploader(
    "Upload de Extratos (CSV/TXT)", 
    accept_multiple_files=True,
    type=['csv', 'txt']
)

if uploaded_files:
    controller = ImportController()
    
    for file in uploaded_files:
        try:
            total, saved = controller.process_file(file)
            if saved > 0:
                st.success(f"{file.name}: {saved} novos registros salvos de {total} lidos.")
            elif total > 0:
                st.warning(f"{file.name}: {total} lidos, mas todos já existiam no banco.")
            else:
                st.error(f"{file.name}: Nenhum dado lido.")
        except Exception as e:
            st.error(f"Erro em {file.name}: {e}")

# 2. Resumo Rápido
db = DatabaseManager()
all_data = db.get_all_transactions()

if not all_data.empty:
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Transações", len(all_data))
    
    pending = all_data[all_data['category'].isnull()]
    c2.metric("Pendentes de Classificação", len(pending), delta_color="inverse")
    
    last_date = pd.to_datetime(all_data['date']).max()
    c3.metric("Última Data", last_date.strftime("%d/%m/%Y"))