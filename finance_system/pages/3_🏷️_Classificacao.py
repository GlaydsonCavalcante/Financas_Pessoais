import streamlit as st
import sys
import os

# --- CORREÇÃO DE PATH ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)
# ------------------------

from src.services.categorizer_service import CategorizerService

st.set_page_config(page_title="Classificação", layout="wide")

service = CategorizerService()
CATEGORY_IGNORE = "⛔ IGNORADO"  # Constante para itens excluídos

st.title("🏷️ Classificação Inteligente")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📚 Memória")
    existing_cats = service.get_unique_categories()
    if not existing_cats.empty:
        # Filtra para não mostrar o IGNORADO na lista de sugestões úteis
        clean_list = existing_cats[existing_cats['Categoria'] != CATEGORY_IGNORE]
        st.dataframe(clean_list, hide_index=True, use_container_width=True, height=400)

st.markdown("---")

tab_pendencias, tab_regras = st.tabs(["📝 Pendências", "⚙️ Gerenciar Regras"])

# --- TAB 1: PENDÊNCIAS ---
with tab_pendencias:
    auto_count = service.run_auto_classification()
    if auto_count > 0:
        st.toast(f"🤖 {auto_count} itens processados automaticamente!")

    pending_df = service.get_pending_transactions()
    
    if pending_df.empty:
        st.success("✅ Tudo limpo! Nenhuma pendência.")
    else:
        st.info(f"Pendências: {len(pending_df)}")
        
        col_list, col_action = st.columns([2, 1])
        
        with col_list:
            unique_descs = pending_df['description'].unique()
            selected_desc = st.selectbox("Item para classificar:", unique_descs)
            
            # Filtra e cria uma cópia para não afetar o original
            affected_rows = pending_df[pending_df['description'] == selected_desc].copy()
            st.markdown(f"**Ocorrências:** {len(affected_rows)}")
            
            # --- NOVA LÓGICA DE FORMATAÇÃO DE ORIGEM ---
            def format_source(val):
                val = str(val).lower()
                if 'csv' in val: return 'Conta Corrente'
                if 'card' in val or 'txt' in val: return 'Cartão Visa'
                if 'contrato' in val: return 'Empréstimo'
                return 'Outros'

            # Cria a coluna amigável apenas para exibição
            affected_rows['Origem'] = affected_rows['source'].apply(format_source)
            
            # Exibe a tabela com a nova coluna no meio
            st.dataframe(
                affected_rows[['date', 'Origem', 'amount']], 
                column_config={
                    "date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "amount": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    "Origem": st.column_config.TextColumn("Conta/Cartão")
                },
                use_container_width=True,
                hide_index=True
            )

        with col_action:
            # --- ZONA DE DECISÃO ---
            with st.container(border=True):
                st.subheader("Ação")
                st.markdown(f"Termo: **{selected_desc}**")
                
                # Seletor de Modo (Aplica a Categorizar ou Ignorar)
                apply_mode = st.radio(
                    "Alcance da Ação:",
                    ["Criar Regra (Todo o Histórico)", "Apenas estes (Pontual)"],
                    horizontal=True
                )
                
                # OPÇÃO 1: CLASSIFICAR
                c1, c2 = st.columns([3, 1])
                new_category = c1.text_input("Categoria:", placeholder="Ex: Mercado", label_visibility="collapsed")
                
                if c2.button("💾", help="Salvar Categoria", type="primary"):
                    if not new_category:
                        st.error("Digite o nome.")
                    else:
                        if "Criar Regra" in apply_mode:
                            service.create_rule(selected_desc, new_category)
                            st.success(f"Regra criada: {new_category}")
                        else:
                            for hash_id in affected_rows['hash_id']:
                                service.manual_update(hash_id, new_category)
                            st.success("Salvo manualmente.")
                        st.rerun()

                # OPÇÃO 2: EXCLUIR (IGNORAR)
                if st.button(f"{CATEGORY_IGNORE}", use_container_width=True):
                    if "Criar Regra" in apply_mode:
                        service.create_rule(selected_desc, CATEGORY_IGNORE)
                        st.warning(f"Item banido! Regra criada para ignorar '{selected_desc}'.")
                    else:
                        for hash_id in affected_rows['hash_id']:
                            service.manual_update(hash_id, CATEGORY_IGNORE)
                        st.warning("Itens ignorados manualmente.")
                    st.rerun()

# --- TAB 2: REGRAS ---
with tab_regras:
    st.markdown("### Regras Ativas")
    rules_df = service.get_rules()
    
    if rules_df.empty:
        st.info("Sem regras.")
    else:
        for index, row in rules_df.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.text(row['match_term'])
            with c2:
                # Destaque visual se for regra de exclusão
                if row['target_category'] == CATEGORY_IGNORE:
                    st.error(row['target_category'])
                else:
                    st.caption(row['target_category'])
            with c3:
                if st.button("🗑️", key=f"del_{index}"):
                    service.delete_rule(row['match_term'])
                    st.rerun()
            st.divider()