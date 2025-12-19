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

# --- ESTADO (SESSION STATE) ---
if 'vendas_df' not in st.session_state: st.session_state.vendas_df = pd.DataFrame()
if 'compras_df' not in st.session_state: st.session_state.compras_df = pd.DataFrame()
if 'estoque_df' not in st.session_state: st.session_state.estoque_df = pd.DataFrame()
if 'empresa_nome' not in st.session_state: st.session_state.empresa_nome = "Nenhuma Empresa"
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

def reset_all():
    st.session_state.vendas_df = pd.DataFrame()
    st.session_state.compras_df = pd.DataFrame()
    st.session_state.estoque_df = pd.DataFrame()
    st.session_state.empresa_nome = "Nenhuma Empresa"
    st.session_state.uploader_key += 1
    st.rerun()

# --- CSS NUCLEAR (VISUAL NASCEL) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .stApp { background-color: #F5F7F9; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E0E0E0; }
    section[data-testid="stSidebar"] * { color: #2C3E50 !important; }
    section[data-testid="stSidebar"] input { background-color: #FFFFFF !important; color: #2C3E50 !important; }
    .main-header { font-size: 2.2rem; font-weight: 800; color: #1a252f; margin-bottom: 5px; }
    .sub-header { font-size: 1rem; color: #7F8C8D; margin-bottom: 10px; border-bottom: 3px solid #E67E22; display: inline-block; padding-bottom: 5px; }
    .company-badge { background-color: #E67E22; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; margin-bottom: 20px; display: inline-block;}
    div[data-testid="stMetric"] { background-color: #FFFFFF !important; border: 1px solid #E0E0E0; border-radius: 12px; padding: 20px; border-left: 6px solid #E67E22; }
    div[data-testid="stMetricLabel"] p { color: #7F8C8D !important; }
    div[data-testid="stMetricValue"] div { color: #2C3E50 !important; }
    div.stButton > button[kind="primary"] { background-color: #E67E22 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CABEÇALHO ---
col_logo, col_txt = st.columns([0.6, 10])
with col_logo: st.markdown("## 🟧") 
with col_txt:
    st.markdown('<div class="main-header">cClass Auditor AI</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="company-badge">🏢 {st.session_state.empresa_nome}</div>', unsafe_allow_html=True)

# --- CACHE ---
@st.cache_data
def carregar_bases():
    return motor.carregar_base_legal(), motor.carregar_json_regras()

@st.cache_data
def carregar_tipi_cache(file):
    return motor.carregar_tipi(file)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎛️ Parâmetros")
    aliquota_input = st.number_input("Alíquota IBS/CBS (%)", 0.0, 100.0, 26.5, 0.5)
    
    st.divider()
    st.markdown("#### 📂 Importação de Dados")
    
    vendas_files = st.file_uploader("1. XMLs de Vendas (Saída)", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}")
    compras_files = st.file_uploader("2. XMLs de Compras (Entrada)", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}")
    sped_file = st.file_uploader("3. SPED Fiscal (Estoque)", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Limpar Tudo", type="secondary", use_container_width=True):
        reset_all()

    with st.expander("⚙️ Base de Dados"):
        uploaded_tipi = st.file_uploader("Atualizar TIPI", type=['xlsx', 'csv'])
        if st.button("Recarregar Regras"):
            carregar_bases.clear()
            st.rerun()

    with st.spinner("Carregando bases..."):
        mapa_lei, df_regras_json = carregar_bases()
        df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- PROCESSAMENTO ---
def processar_arquivos(arquivos, tipo, ns):
    lista = []
    for arquivo in arquivos:
        try:
            tree = ET.parse(arquivo)
            if tipo == 'SAIDA' and st.session_state.empresa_nome == "Nenhuma Empresa":
                st.session_state.empresa_nome = motor.extrair_nome_empresa_xml(tree, ns)
            itens = motor.processar_xml_detalhado(tree, ns, tipo)
            lista.extend(itens)
        except: continue
    return lista

ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

if vendas_files and st.session_state.vendas_df.empty:
    with st.spinner("Processando Vendas..."):
        itens = processar_arquivos(vendas_files, 'SAIDA', ns)
        if itens: st.session_state.vendas_df = pd.DataFrame(itens)

if compras_files and st.session_state.compras_df.empty:
    with st.spinner("Processando Compras..."):
        itens = processar_arquivos(compras_files, 'ENTRADA', ns)
        if itens: st.session_state.compras_df = pd.DataFrame(itens)

if sped_file and st.session_state.estoque_df.empty:
    with st.spinner("Processando SPED..."):
        nome, itens = motor.processar_sped_fiscal(sped_file)
        st.session_state.empresa_nome = nome
        if itens: st.session_state.estoque_df = pd.DataFrame(itens)

# --- AUDITORIA ---
def auditar_df(df, aliquota):
    if df.empty: return df
    res = df.apply(
        lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliquota), 
        axis=1, result_type='expand'
    )
    df[['cClassTrib', 'Descrição', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada']] = res
    return df

df_vendas_aud = auditar_df(st.session_state.vendas_df.copy(), aliquota_input/100)
df_compras_aud = auditar_df(st.session_state.compras_df.copy(), aliquota_input/100)
df_estoque_aud = auditar_df(st.session_state.estoque_df.copy(), aliquota_input/100)

# --- VISUALIZAÇÃO ---
if not df_vendas_aud.empty or not df_compras_aud.empty or not df_estoque_aud.empty:
    
    # KPIs DE APURAÇÃO
    st.markdown("### ⚖️ Simulação de Apuração (Não-Cumulatividade)")
    debito_total = df_vendas_aud['Carga Projetada'].sum() if not df_vendas_aud.empty else 0.0
    credito_total = df_compras_aud['Carga Projetada'].sum() if not df_compras_aud.empty else 0.0
    saldo = debito_total - credito_total
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Débitos (Vendas)", f"R$ {debito_total:,.2f}", delta="Passivo", delta_color="inverse")
    st.markdown("""<style>div[data-testid="metric-container"]:nth-child(2) {border-left: 6px solid #27AE60 !important;}</style>""", unsafe_allow_html=True)
    c2.metric("Créditos (Compras)", f"R$ {credito_total:,.2f}", delta="Ativo", delta_color="normal")
    c3.metric("Saldo Final", f"R$ {abs(saldo):,.2f}", delta="A Pagar" if saldo > 0 else "Credor", delta_color="inverse")
    
    itens_com_erro = 0
    if not df_vendas_aud.empty: itens_com_erro += len(df_vendas_aud[df_vendas_aud['Validação TIPI'].str.contains("Ausente")])
    if not df_estoque_aud.empty: itens_com_erro += len(df_estoque_aud[df_estoque_aud['Validação TIPI'].str.contains("Ausente")])
    c4.metric("Auditoria TIPI", itens_com_erro, delta="Itens Suspeitos" if itens_com_erro > 0 else "Cadastro OK", delta_color="inverse")

    st.divider()

    # --- CONFIGURAÇÃO DAS TABELAS (O PULO DO GATO VISUAL) ---
    col_config_padrao = {
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
        "Status": st.column_config.TextColumn("Regra Aplicada", width="medium"),
        
        # AQUI ESTÁ A MÁGICA DA AUDITORIA:
        "Novo CST": st.column_config.TextColumn("Novo CST", help="CST sugerido conforme LCP 214"),
        "cClassTrib": st.column_config.TextColumn("Class. Tributária", help="Código NBS/NCM Tributável"),
        "Validação TIPI": st.column_config.TextColumn("TIPI", width="small")
    }

    tabs = st.tabs(["📤 Vendas (Auditado)", "📥 Compras (Auditado)", "📦 Estoque (SPED)", "📊 Detalhes"])
    
    with tabs[0]:
        if not df_vendas_aud.empty:
            st.dataframe(
                df_vendas_aud, 
                use_container_width=True, 
                hide_index=True,
                column_config=col_config_padrao
            )
        else: st.info("Sem dados de Venda.")
            
    with tabs[1]:
        if not df_compras_aud.empty:
            st.dataframe(
                df_compras_aud, 
                use_container_width=True, 
                hide_index=True,
                column_config=col_config_padrao
            )
        else: st.info("Sem dados de Compra.")
        
    with tabs[2]:
        if not df_estoque_aud.empty:
            # Mostra colunas específicas para cadastro
            cols_estoque = ['Cód. Produto', 'NCM', 'Produto', 'Status', 'Novo CST', 'cClassTrib', 'Validação TIPI']
            st.dataframe(
                df_estoque_aud[cols_estoque], 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn("Regra Auditada", width="medium"),
                    "Novo CST": st.column_config.TextColumn("Sugestão CST", width="small"),
                }
            )
        else: st.info("Sem dados de SPED.")
        
    with tabs[3]:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            if not df_vendas_aud.empty: df_vendas_aud.to_excel(writer, index=False, sheet_name="Vendas_Debitos")
            if not df_compras_aud.empty: df_compras_aud.to_excel(writer, index=False, sheet_name="Compras_Creditos")
            if not df_estoque_aud.empty: df_estoque_aud.to_excel(writer, index=False, sheet_name="Estoque_Cadastro")
            
            resumo = pd.DataFrame([{
                'Total Débitos': debito_total,
                'Total Créditos': credito_total,
                'Saldo Final': saldo
            }])
            resumo.to_excel(writer, index=False, sheet_name="Resumo_Apuracao")

        st.download_button("📥 BAIXAR RELATÓRIO COMPLETO (.XLSX)", buffer, "Auditoria_Completa_Nascel.xlsx", "primary", use_container_width=True)

else:
    st.info("Utilize a barra lateral para carregar XMLs ou SPED.")