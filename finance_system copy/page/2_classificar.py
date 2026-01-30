import streamlit as st
from src.database import DatabaseManager
from src.controllers.categorizer import CategorizerEngine

st.set_page_config(page_title="Classificar", layout="wide")

db = DatabaseManager()
engine = CategorizerEngine()

st.title("🏷️ Fluxo de Classificação")

# 1. Executa Auto-Classificação na entrada para garantir frescor
auto_count = engine.run_auto_classification()
if auto_count > 0:
    st.toast(f"🤖 {auto_count} itens classificados automaticamente via regras.")

# 2. Busca Pendências
pending = db.get_pending_transactions()

if pending.empty:
    st.success("✅ Tudo limpo! Nenhuma transação pendente.")
    st.balloons()
else:
    st.warning(f"⚠️ {len(pending)} transações aguardam sua decisão.")
    
    # 3. Interface de Trabalho
    # Agrupamos por descrição para resolver múltiplos itens de uma vez
    unique_descs = pending['description'].unique()
    
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        selected_desc = st.selectbox(
            "Selecione uma despesa para resolver:", 
            unique_descs,
            index=0
        )
        
        # Mostra as transações afetadas
        affected_rows = pending[pending['description'] == selected_desc]
        st.markdown(f"**Itens encontrados:** {len(affected_rows)}")
        st.dataframe(
            affected_rows[['date', 'amount', 'source_file']], 
            use_container_width=True,
            hide_index=True
        )

    with col_right:
        st.markdown("### Decisão")
        st.info(f"Termo: **{selected_desc}**")
        
        new_category = st.text_input("Definir Categoria:", placeholder="Ex: Alimentação")
        
        # Opções de Regra
        st.markdown("---")
        rule_mode = st.radio(
            "Como aplicar?",
            ["Criar Regra (Todo o Histórico)", "Apenas estes itens (Pontual)"],
            index=0
        )
        
        if st.button("Aplicar Classificação", type="primary"):
            if not new_category:
                st.error("Digite uma categoria.")
            else:
                if "Criar Regra" in rule_mode:
                    # Cria regra e o motor reprocessa tudo
                    engine.create_new_rule(selected_desc, new_category)
                    st.success(f"Regra criada para '{selected_desc}'!")
                else:
                    # Aplicação Manual (Trava de Segurança)
                    for _, row in affected_rows.iterrows():
                        db.update_transaction_category(
                            row['hash_id'], 
                            new_category, 
                            is_manual=True # <--- AQUI ESTÁ A SUA EXIGÊNCIA
                        )
                    st.success("Itens atualizados manualmente.")
                
                st.rerun()