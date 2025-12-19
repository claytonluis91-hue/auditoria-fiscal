import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor # Importa o arquivo que criamos acima

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="cClass Auditor AI",
    page_icon="🟧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS PROFISSIONAL
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
    html, body, [class*="css"] {font-family: 'Roboto', sans-serif;}
    .stMarkdown p, .stMarkdown li, .stDataFrame, div[data-testid="stMarkdownContainer"] p {
        color: #333333 !important; font-size: 1rem;
    }
    .main-header {
        font-size: 2.8rem; font-weight: 800; color: #2C3E50; margin-bottom: 0px; letter-spacing: -1px;
    }
    .sub-header-line {
        height: 4px; width: 100px; background-color: #EF6C00; margin-bottom: 2rem; margin-top: 5px; border-radius: 2px;
    }
    div[data-testid="stMetric"] {
        background-color: #ffffff; border: 1px solid #dcdcdc; border-radius: 8px; padding: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 6px solid #EF6C00; transition: all 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px); box-shadow: 0 8px 15px rgba(239, 108, 0, 0.15);
    }
    div[data-testid="stMetricLabel"] {color: #546E7A; font-size: 0.9rem; font-weight: 600;}
    div[data-testid="stMetricValue"] {color: #2C3E50; font-weight: 800;}
    div.stButton > button:first-child {
        background-color: #EF6C00; color: white; border-radius: 6px; border: none; padding: 0.6rem 1.2rem;
        font-weight: 700; text-transform: uppercase; transition: background-color 0.3s;
    }
    div.stButton > button:first-child:hover {background-color: #E65100; box-shadow: 0 4px 10px rgba(0,0,0,0.2);}
    section[data-testid="stSidebar"] {background-color: #F4F6F7; border-right: 1px solid #CFD8DC;}
    </style>
    """, unsafe_allow_html=True)

# --- CABEÇALHO ---
col1, col2 = st.columns([0.5, 8])
with col1: st.markdown("## 🟧") 
with col2:
    st.markdown('<div class="main-header">cClass Auditor AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header-line"></div>', unsafe_allow_html=True)

# --- CACHE (Usa funções do motor) ---
@st.cache_data
def carregar_bases():
    lei = motor.carregar_base_legal()
    json_regras = motor.carregar_json_regras()
    return lei, json_regras

@st.cache_data
def carregar_tipi_cache(file):
    return motor.carregar_tipi(file)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎛️ Painel de Controle")
    aliquota_input = st.number_input("Alíquota IBS/CBS (%)", 0.0, 100.0, 26.5, 0.5)
    uploaded_xmls = st.file_uploader("📂 Arraste os XMLs de Venda", type=['xml'], accept_multiple_files=True)
    
    with st.expander("⚙️ Configurações Avançadas"):
        uploaded_tipi = st.file_uploader("Atualizar Tabela TIPI", type=['xlsx', 'csv'])
        if st.button("Recarregar Regras da Lei"):
            carregar_bases.clear()
            st.rerun()
            
    st.divider()
    with st.spinner("Sincronizando bases..."):
        mapa_lei, df_regras_json = carregar_bases()
        df_tipi = carregar_tipi_cache(uploaded_tipi)
        
    st.markdown(f"""
    <div style='background-color:#ffffff; padding:10px; border-radius:5px; border-left: 4px solid #EF6C00; border: 1px solid #e0e0e0;'>
        <small style='color: #333333;'><b>STATUS DO SISTEMA</b><br>
        ⚖️ Regras Ativas: <b>{len(mapa_lei)}</b><br>
        💰 Alíquota Base: <b>{aliquota_input}%</b><br>
        📚 Validação TIPI: <b>{'Ativa ✅' if not df_tipi.empty else 'Inativa ⚠️'}</b></small>
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
        
        # Chama a função de classificação que está no MOTOR
        resultados = df_analise.apply(
            lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliquota_input/100), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada']] = resultados
        
        # Diferença (Impacto)
        df_analise['Impacto Financeiro'] = df_analise['Carga Projetada'] - df_analise['Carga Atual']
        
        cols_principal = ['Cód. Produto', 'NCM', 'Produto', 'CFOP', 'Valor', 'Status', 'Carga Atual', 'Carga Projetada', 'Impacto Financeiro', 'Novo CST', 'cClassTrib', 'Origem Legal', 'Validação TIPI']
        df_principal = df_analise[cols_principal]
        df_arquivos = df_base[['Chave NFe']].drop_duplicates().reset_index(drop=True)
        df_arquivos.columns = ['Arquivos Processados']
        
        st.markdown("### 📊 Planejamento Tributário (Atual vs Reforma)")
        
        total_atual = df_principal['Carga Atual'].sum()
        total_futuro = df_principal['Carga Projetada'].sum()
        variacao = total_futuro - total_atual
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Base Auditada (vProd)", f"R$ {df_principal['Valor'].sum():,.2f}")
        c2.metric("Carga Atual (ICMS+PIS+COFINS)", f"R$ {total_atual:,.2f}")
        
        percentual = ((total_futuro/total_atual)-1)*100 if total_atual > 0 else 0
        c3.metric("Carga Projetada (IBS+CBS)", f"R$ {total_futuro:,.2f}", 
                  delta=f"{percentual:.1f}%",
                  delta_color="inverse")
        
        c4.metric("Impacto Financeiro", f"R$ {abs(variacao):,.2f}", 
                  delta="Aumento de Carga" if variacao > 0 else "Redução de Carga",
                  delta_color="inverse")

        st.markdown("---")
        
        tab1, tab2, tab3 = st.tabs(["📋 Comparativo Item a Item", "📂 Arquivos", "🔍 Itens com Benefício"])
        with tab1: st.dataframe(df_principal, use_container_width=True)
        with tab2: st.dataframe(df_arquivos, use_container_width=True)
        with tab3: st.dataframe(df_principal[df_principal['Origem Legal'].str.contains("Anexo")], use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_principal.to_excel(writer, index=False, sheet_name="Planejamento Tributario")
            df_arquivos.to_excel(writer, index=False, sheet_name="Arquivos")
            if not df_tipi.empty:
                df_principal[df_principal['Validação TIPI'].str.contains("Ausente")].to_excel(writer, index=False, sheet_name="Erros Cadastro")
        
        st.download_button(
            label="📥 BAIXAR ESTUDO DE IMPACTO (.xlsx)",
            data=buffer,
            file_name="Planejamento_Tributario_Nascel_v23.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        
        st.markdown("---")
        st.markdown("#### 📈 Distribuição da Nova Carga Tributária")
        chart_data = df_principal['Status'].value_counts()
        st.bar_chart(chart_data, color="#EF6C00")