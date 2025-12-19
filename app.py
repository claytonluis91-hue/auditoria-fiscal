import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor 

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(
    page_title="cClass Auditor AI",
    page_icon="🟧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Controle de Sessão
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_app():
    st.session_state.uploader_key += 1
    st.rerun()

# --- CSS CORRIGIDO (BARRA LATERAL ESCURA) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* 1. GERAL */
    .stApp { background-color: #F5F7F9; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }

    /* 2. BARRA LATERAL (CORREÇÃO DE CONTRASTE) */
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E0E0E0;
    }
    
    /* Força cor escura em TODOS os elementos de texto da Sidebar */
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span, 
    section[data-testid="stSidebar"] label, 
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p {
        color: #333333 !important; /* Cinza Quase Preto */
    }
    
    /* Ajuste específico para os labels dos inputs (Upload e Número) */
    section[data-testid="stSidebar"] .stWidgetLabel p {
        color: #1a252f !important;
        font-weight: 600;
        font-size: 0.95rem;
    }

    /* 3. CABEÇALHO E TÍTULOS */
    .main-header { font-size: 2.2rem; font-weight: 800; color: #1a252f; margin-bottom: 5px; letter-spacing: -0.5px; }
    .sub-header { font-size: 1rem; color: #7F8C8D; margin-bottom: 25px; border-bottom: 3px solid #E67E22; display: inline-block; padding-bottom: 5px; }

    /* 4. CARDS DE MÉTRICAS */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF !important; border: 1px solid #E0E0E0; border-radius: 12px; padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.04); position: relative; overflow: hidden;
    }
    div[data-testid="stMetric"]::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px; background-color: #E67E22; }
    div[data-testid="stMetricLabel"] p { color: #7F8C8D !important; font-size: 0.85rem !important; font-weight: 600; text-transform: uppercase; }
    div[data-testid="stMetricValue"] div { color: #2C3E50 !important; font-weight: 800; font-size: 1.8rem !important; }

    /* 5. BOTÕES */
    div.stButton > button { border-radius: 8px; font-weight: 600; border: none; transition: all 0.3s; }
    div.stButton > button[kind="primary"] { background-color: #E67E22; color: white; }
    div.stButton > button[kind="primary"]:hover { background-color: #D35400; box-shadow: 0 4px 10px rgba(230, 126, 34, 0.3); }
    div.stButton > button[kind="secondary"] { background-color: #ECF0F1; color: #2C3E50; border: 1px solid #BDC3C7; }
    div.stButton > button[kind="secondary"]:hover { background-color: #BDC3C7; }

    /* 6. STATUS BOX */
    .status-box {
        background-color: #FEF9E7; border: 1px solid #F1C40F; border-radius: 8px; padding: 15px;
        color: #333333; /* Texto escuro forçado */
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CABEÇALHO ---
col_logo, col_txt = st.columns([0.6, 10])
with col_logo: st.markdown("## 🟧") 
with col_txt:
    st.markdown('<div class="main-header">cClass Auditor AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Planejamento Tributário & Auditoria Fiscal</div>', unsafe_allow_html=True)

# --- CACHE ---
@st.cache_data
def carregar_bases():
    lei = motor.carregar_base_legal()
    json_regras = motor.carregar_json_regras()
    return lei, json_regras

@st.cache_data
def carregar_tipi_cache(file):
    return motor.carregar_tipi(file)

# --- SIDEBAR (AGORA COM TEXTO ESCURO) ---
with st.sidebar:
    st.markdown("### 🎛️ Parâmetros")
    
    aliquota_input = st.number_input("Alíquota IBS/CBS (%)", 0.0, 100.0, 26.5, 0.5)
    
    st.divider()
    
    uploaded_xmls = st.file_uploader(
        "📂 Carregar XMLs de Venda", 
        type=['xml'], 
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}"
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🔄 Nova Auditoria / Limpar", type="secondary", use_container_width=True):
        reset_app()

    with st.expander("⚙️ Base de Dados (Opcional)"):
        uploaded_tipi = st.file_uploader("Atualizar TIPI", type=['xlsx', 'csv'])
        if st.button("Recarregar Regras"):
            carregar_bases.clear()
            st.rerun()

    with st.spinner("Carregando motor fiscal..."):
        mapa_lei, df_regras_json = carregar_bases()
        df_tipi = carregar_tipi_cache(uploaded_tipi)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="status-box">
        <b>STATUS DO SISTEMA</b><br>
        ✅ Regras Carregadas: {len(mapa_lei)}<br>
        {'✅ Validação TIPI Ativa' if not df_tipi.empty else '⚠️ TIPI Offline'}
    </div>
    """, unsafe_allow_html=True)

# --- PROCESSAMENTO ---
if uploaded_xmls:
    lista_itens = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    bar_progresso = st.progress(0)
    
    for i, arquivo in enumerate(uploaded_xmls):
        try:
            tree = ET.parse(arquivo)
            itens_nota = motor.processar_xml_detalhado(tree, ns)
            lista_itens.extend(itens_nota)
        except: continue
        bar_progresso.progress((i+1)/len(uploaded_xmls))
        
    bar_progresso.empty()
    
    if lista_itens:
        df_base = pd.DataFrame(lista_itens)
        df_analise = df_base.drop_duplicates(subset=['Cód. Produto', 'NCM', 'CFOP']).copy()
        
        resultados = df_analise.apply(
            lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliquota_input/100), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada']] = resultados
        df_analise['Impacto Financeiro'] = df_analise['Carga Projetada'] - df_analise['Carga Atual']
        
        cols_principal = ['Cód. Produto', 'NCM', 'Produto', 'CFOP', 'Valor', 'Status', 'Carga Atual', 'Carga Projetada', 'Impacto Financeiro', 'Novo CST', 'cClassTrib', 'Origem Legal', 'Validação TIPI']
        df_principal = df_analise[cols_principal]
        
        df_arquivos = df_base[['Chave NFe']].drop_duplicates().reset_index(drop=True)
        df_arquivos.columns = ['Chaves Processadas']
        
        # --- DASHBOARD ---
        st.markdown("### 📊 Visão Geral do Impacto")
        
        total_atual = df_principal['Carga Atual'].sum()
        total_futuro = df_principal['Carga Projetada'].sum()
        variacao = total_futuro - total_atual
        percentual = ((total_futuro/total_atual)-1) if total_atual > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Volume Auditado (vProd)", f"R$ {df_principal['Valor'].sum():,.2f}")
        c2.metric("Carga Atual (ICMS/PIS/COFINS)", f"R$ {total_atual:,.2f}")
        c3.metric("Carga Projetada (IBS/CBS)", f"R$ {total_futuro:,.2f}", delta=f"{percentual:.1%}", delta_color="inverse")
        c4.metric("Impacto Financeiro", f"R$ {abs(variacao):,.2f}", delta="Aumento" if variacao > 0 else "Economia", delta_color="inverse")
        
        st.divider()

        tab1, tab2, tab3 = st.tabs(["📋 Auditoria Detalhada", "📂 Arquivos", "🔍 Itens com Benefício"])
        
        with tab1:
            st.dataframe(
                df_principal,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Impacto Financeiro": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Status": st.column_config.TextColumn("Classificação", help="Regra aplicada"),
                    "Validação TIPI": st.column_config.TextColumn("TIPI", width="small")
                }
            )
            
        with tab2: st.dataframe(df_arquivos, use_container_width=True, hide_index=True)
            
        with tab3: 
            df_beneficio = df_principal[df_principal['Origem Legal'].str.contains("Anexo")]
            st.dataframe(
                df_beneficio, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Carga Projetada": st.column_config.ProgressColumn(
                        "Carga Projetada",
                        format="R$ %.2f",
                        min_value=0,
                        max_value=df_principal['Carga Projetada'].max(),
                    )
                }
            )

        col_down, col_graph = st.columns([1, 2])
        
        with col_down:
            st.markdown("### 📥 Exportar")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_principal.to_excel(writer, index=False, sheet_name="Planejamento Tributario")
                df_arquivos.to_excel(writer, index=False, sheet_name="Arquivos")
                if not df_tipi.empty:
                    df_principal[df_principal['Validação TIPI'].str.contains("Ausente")].to_excel(writer, index=False, sheet_name="Erros Cadastro")
            
            st.download_button(
                label="BAIXAR RELATÓRIO (.XLSX)",
                data=buffer,
                file_name="Planejamento_Tributario_Nascel.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            
        with col_graph:
            st.markdown("### 📈 Distribuição da Nova Carga")
            chart_data = df_principal['Status'].value_counts().reset_index()
            chart_data.columns = ['Classificação', 'Qtd Itens']
            st.bar_chart(chart_data, x="Classificação", y="Qtd Itens", color="#E67E22")

else:
    st.info("👋 Bem-vindo ao Auditor Nascel. Arraste seus arquivos XML na barra lateral para começar.")