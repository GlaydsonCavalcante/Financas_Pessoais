import streamlit as st
import pandas as pd
from src.controllers.importer import ImportController

st.set_page_config(page_title="Finanças Modo Absoluto", layout="wide")

st.title("Ingestão de Extratos Financeiros")
st.markdown("---")

# 1. Upload Area
uploaded_files = st.file_uploader(
    "Arraste extratos (CSV, TXT, PDF)", 
    accept_multiple_files=True,
    type=['csv', 'txt', 'pdf']
)

if uploaded_files:
    controller = ImportController()
    all_transactions = []
    
    # 2. Processing Loop
    for file in uploaded_files:
        try:
            transactions = controller.process_file(file)
            all_transactions.extend(transactions)
            st.success(f"{file.name}: Processado ({len(transactions)} registros)")
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {str(e)}")

    # 3. Validation View
    if all_transactions:
        # Converte objetos para dicionários para exibição
        data = [t.to_dict() for t in all_transactions]
        df = pd.DataFrame(data)
        
        st.subheader("Checkpoint de Validação")
        st.dataframe(
            df.sort_values(by="Data", ascending=False), 
            use_container_width=True,
            height=600
        )
        
        st.metric("Total Processado", f"R$ {df['Valor'].sum():,.2f}")