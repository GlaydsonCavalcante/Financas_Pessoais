import streamlit as st
from src.services.importer_service import ImporterService

st.set_page_config(page_title="Importar Extratos", layout="centered")

st.title("📥 Central de Extratos")
st.markdown("---")

st.info("Suporta: **CSV** (Conta Corrente BB) e **TXT** (Fatura Cartão via SISBB).")

# Widget de Upload
uploaded_files = st.file_uploader(
    "Arraste seus arquivos aqui", 
    accept_multiple_files=True,
    type=['csv', 'txt']
)

if uploaded_files:
    if st.button("Processar Arquivos", type="primary", use_container_width=True):
        service = ImporterService()
        
        with st.spinner("Lendo e normalizando dados..."):
            results = service.process_files(uploaded_files)
        
        # Exibição de Resultados
        if results["errors"]:
            for err in results["errors"]:
                st.error(err)
        
        if results["read"] == 0 and not results["errors"]:
            st.warning("Arquivos processados, mas nenhuma transação válida encontrada.")
        else:
            col1, col2 = st.columns(2)
            col1.metric("Lidos", results["read"])
            col2.metric("Novos Salvos", results["saved"], delta_color="normal")
            
            if results["saved"] < results["read"]:
                st.caption(f"Nota: {results['read'] - results['saved']} itens duplicados foram ignorados.")
            
            if results["saved"] > 0:
                st.success("Importação concluída com sucesso!")
                st.balloons()