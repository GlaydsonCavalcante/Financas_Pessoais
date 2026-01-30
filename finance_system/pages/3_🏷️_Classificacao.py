import streamlit as st
from src.services.categorizer_service import CategorizerService

st.set_page_config(page_title="Classificação", layout="wide")

service = CategorizerService()

st.title("🏷️ Classificação Inteligente")
st.markdown("---")

# 1. Tabs para separar Fluxo de Trabalho de Gestão
tab_pendencias, tab_regras = st.tabs(["📝 Pendências", "⚙️ Gerenciar Regras"])

# --- TAB 1: PENDÊNCIAS ---
with tab_pendencias:
    # Auto-executa regras ao abrir
    auto_count = service.run_auto_classification()
    if auto_count > 0:
        st.toast(f"🤖 {auto_count} itens classificados automaticamente!")

    pending_df = service.get_pending_transactions()
    
    if pending_df.empty:
        st.success("✅ Zero Pendências! Seu fluxo está em dia.")
        st.balloons()
    else:
        st.info(f"Você tem {len(pending_df)} transações aguardando definição.")
        
        # Layout de Trabalho: Esquerda (Lista) | Direita (Ação)
        col_list, col_action = st.columns([2, 1])
        
        with col_list:
            # Agrupa por descrição para facilitar (Ex: 10 Ubers viram 1 linha)
            unique_descs = pending_df['description'].unique()
            selected_desc = st.selectbox("Selecione um item para resolver:", unique_descs)
            
            # Mostra as transações afetadas
            affected_rows = pending_df[pending_df['description'] == selected_desc]
            st.markdown(f"**Ocorrências:** {len(affected_rows)}")
            st.dataframe(
                affected_rows[['date', 'amount', 'source']], 
                use_container_width=True,
                hide_index=True
            )

        with col_action:
            with st.container(border=True):
                st.subheader("Decisão")
                st.markdown(f"Termo: **{selected_desc}**")
                
                new_category = st.text_input("Categoria:", placeholder="Ex: Transporte")
                
                # Opções de Aplicação
                apply_mode = st.radio(
                    "Como aplicar?",
                    ["Criar Regra (Aprender)", "Apenas estes (Manual)"],
                    help="Criar Regra automatiza isso no futuro."
                )
                
                if st.button("Aplicar", type="primary", use_container_width=True):
                    if not new_category:
                        st.error("Digite uma categoria.")
                    else:
                        if "Criar Regra" in apply_mode:
                            # O termo de match é a descrição selecionada
                            # (Futuro: Permitir editar o termo para ser mais genérico)
                            service.create_rule(selected_desc, new_category)
                            st.success(f"Regra criada! '{selected_desc}' -> {new_category}")
                        else:
                            # Loop para atualizar manualmente ID por ID
                            for hash_id in affected_rows['hash_id']:
                                service.manual_update(hash_id, new_category)
                            st.success("Itens atualizados manualmente.")
                        
                        st.rerun()

# --- TAB 2: REGRAS ---
with tab_regras:
    st.markdown("### Regras de Aprendizado")
    rules_df = service.get_rules()
    
    if rules_df.empty:
        st.info("Nenhuma regra criada ainda.")
    else:
        # Exibição editável (apenas para deleção visualmente)
        for index, row in rules_df.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.text(row['match_term'])
            with c2:
                st.caption(row['target_category'])
            with c3:
                if st.button("🗑️", key=f"del_{index}"):
                    service.delete_rule(row['match_term'])
                    st.rerun()
            st.divider()