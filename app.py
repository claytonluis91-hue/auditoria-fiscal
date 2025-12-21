import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor 
import importlib
import relatorio

# CACHE FIX
importlib.reload(motor)
importlib.reload(relatorio)

# --- CONFIGURAÇÃO ---
st.set_page_config(
    page_title="cClass Auditor AI",
    page_icon="🟧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- ESTADO ---
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

# --- CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .stApp { background-color: #F8F9FA; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E0E0E0; }
    section[data-testid="stSidebar"] * { color: #2C3E50 !important; }
    .main-header { font-size: 2.5rem; font-weight: 800; color: #1a252f; text-align: center; margin-top: 20px;}
    .company-badge { background-color: #E67E22; color: white; padding: 5px 20px; border-radius: 20px; font-weight: bold; font-size: 1rem; display: block; margin: 0 auto 20px auto; width: fit-content; }
    .upload-title { font-weight: 700; color: #2C3E50; margin-bottom: 5px; font-size: 1.1rem; }
    .upload-desc { font-size: 0.85rem; color: #7F8C8D; margin-bottom: 10px; }
    div[data-testid="stMetric"] { background-color: #FFFFFF !important; border: 1px solid #E0E0E0; border-radius: 12px; padding: 15px; border-left: 6px solid #E67E22; }
    div.stButton > button[kind="primary"] { background-color: #E67E22 !important; color: white !important; width: 100%; }
    div.stButton > button[kind="secondary"] { background-color: #ECF0F1 !important; color: #2C3E50 !important; width: 100%; border: 1px solid #BDC3C7 !important;}
    </style>
    """, unsafe_allow_html=True)

# --- CACHE ---
@st.cache_data
def carregar_bases():
    return motor.carregar_base_legal(), motor.carregar_json_regras()

@st.cache_data
def carregar_tipi_cache(file):
    return motor.carregar_tipi(file)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=50)
    st.markdown("### ⚙️ Alíquotas de Referência")
    c1, c2 = st.columns(2)
    with c1: aliq_ibs = st.number_input("IBS (%)", 0.0, 50.0, 17.7, 0.1)
    with c2: aliq_cbs = st.number_input("CBS (%)", 0.0, 50.0, 8.8, 0.1)
    
    st.divider()
    with st.expander("Atualizar TIPI"):
        uploaded_tipi = st.file_uploader("TIPI (.xlsx)", type=['xlsx', 'csv'])
        if st.button("Recarregar"):
            carregar_bases.clear()
            st.rerun()
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR TUDO", type="secondary"):
        reset_all()
        st.rerun()

    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- BODY ---
st.markdown('<div class="main-header">cClass Auditor AI</div>', unsafe_allow_html=True)
if st.session_state.empresa_nome != "Nenhuma Empresa":
    st.markdown(f'<div class="company-badge">🏢 {st.session_state.empresa_nome}</div>', unsafe_allow_html=True)

modo_selecionado = st.radio("Origem dos Dados:", ["📄 XML (Notas Fiscais)", "📝 SPED Fiscal (TXT)"], horizontal=True, label_visibility="collapsed")
st.markdown("---")

ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

# === FUNÇÃO DE PROCESSAMENTO COM BARRA DE PROGRESSO ===
def processar_arquivos_com_barra(arquivos, tipo):
    lista = []
    total_arquivos = len(arquivos)
    
    # Cria a barra de progresso na tela
    barra = st.progress(0, text=f"Iniciando leitura de {total_arquivos} arquivos...")
    
    for i, arquivo in enumerate(arquivos):
        # Atualiza a barra (i+1 porque o índice começa em 0)
        progresso = (i + 1) / total_arquivos
        barra.progress(progresso, text=f"Processando {i+1} de {total_arquivos} - {arquivo.name}")
        
        try:
            tree = ET.parse(arquivo)
            if tipo == 'SAIDA' and st.session_state.empresa_nome == "Nenhuma Empresa":
                st.session_state.empresa_nome = motor.extrair_nome_empresa_xml(tree, ns)
            lista.extend(motor.processar_xml_detalhado(tree, ns, tipo))
        except: 
            continue
            
    # Limpa a barra quando termina
    barra.empty()
    return lista

if modo_selecionado == "📄 XML (Notas Fiscais)":
    if not st.session_state.estoque_df.empty: 
        st.session_state.estoque_df = pd.DataFrame()
        st.toast("Modo XML ativado.", icon="🔄")

    c_venda, c_compra = st.columns(2)
    with c_venda:
        st.markdown('<div class="upload-title">📤 VENDAS (Saídas)</div>', unsafe_allow_html=True)
        vendas_files = st.file_uploader("Upload Vendas", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}", label_visibility="collapsed")
    with c_compra:
        st.markdown('<div class="upload-title">📥 COMPRAS (Entradas)</div>', unsafe_allow_html=True)
        compras_files = st.file_uploader("Upload Compras", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}", label_visibility="collapsed")

    if vendas_files and st.session_state.vendas_df.empty:
        # Chama a nova função com barra
        st.session_state.vendas_df = pd.DataFrame(processar_arquivos_com_barra(vendas_files, 'SAIDA'))
        st.rerun()

    if compras_files and st.session_state.compras_df.empty:
        # Chama a nova função com barra
        st.session_state.compras_df = pd.DataFrame(processar_arquivos_com_barra(compras_files, 'ENTRADA'))
        st.rerun()

else:
    if not st.session_state.vendas_df.empty:
        st.session_state.vendas_df = pd.DataFrame()
        st.session_state.compras_df = pd.DataFrame()
        st.toast("Modo SPED ativado.", icon="🔄")

    st.markdown('<div class="upload-title" style="text-align:center;">📝 ARQUIVO SPED FISCAL</div>', unsafe_allow_html=True)
    col_sped = st.columns([1, 2, 1])
    with col_sped[1]:
        sped_file = st.file_uploader("Upload SPED", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}", label_visibility="collapsed")

    if sped_file and st.session_state.estoque_df.empty:
        with st.spinner("Lendo e Processando SPED..."):
            nome, itens = motor.processar_sped_fiscal(sped_file)
            st.session_state.empresa_nome = nome
            st.session_state.estoque_df = pd.DataFrame(itens)
            st.rerun()

def auditar_df(df, a_ibs, a_cbs):
    if df.empty: return df
    res = df.apply(
        lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, a_ibs, a_cbs), 
        axis=1, result_type='expand'
    )
    df[['cClassTrib', 'DescRegra', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada', 'vIBS', 'vCBS']] = res
    return df

df_vendas_aud = auditar_df(st.session_state.vendas_df.copy(), aliq_ibs/100, aliq_cbs/100)
df_compras_aud = auditar_df(st.session_state.compras_df.copy(), aliq_ibs/100, aliq_cbs/100)
df_estoque_aud = auditar_df(st.session_state.estoque_df.copy(), aliq_ibs/100, aliq_cbs/100)

tem_dados = not df_vendas_aud.empty or not df_compras_aud.empty or not df_estoque_aud.empty

if tem_dados:
    cols_ordenadas = ['Cód. Produto', 'Descrição Produto', 'NCM', 'CFOP', 'Novo CST', 'cClassTrib', 'DescRegra', 'Valor', 'vICMS', 'vPIS', 'vCOFINS', 'Carga Atual', 'vIBS', 'vCBS', 'Carga Projetada', 'Validação TIPI']
    
    def preparar_exibicao(df):
        if df.empty: return df
        return df.rename(columns={'Produto': 'Descrição Produto'})[cols_ordenadas]

    tabs = st.tabs(["📊 Resumo Executivo", "📤 Saídas", "📥 Entradas", "📂 Arquivos"])

    with tabs[0]:
        st.markdown("### Visão Geral da Apuração")
        debito = df_vendas_aud['Carga Projetada'].sum() if not df_vendas_aud.empty else 0
        credito = df_compras_aud['Carga Projetada'].sum() if not df_compras_aud.empty else 0
        saldo = debito - credito
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Débitos (Saídas)", f"R$ {debito:,.2f}", delta="Passivo", delta_color="inverse")
        st.markdown("""<style>div[data-testid="metric-container"]:nth-child(2) {border-left: 6px solid #27AE60 !important;}</style>""", unsafe_allow_html=True)
        c2.metric("Créditos (Entradas)", f"R$ {credito:,.2f}", delta="Ativo", delta_color="normal")
        c3.metric("Saldo Estimado", f"R$ {abs(saldo):,.2f}", delta="Pagar" if saldo > 0 else "Credor", delta_color="inverse")
        
        total_erros = 0
        if not df_vendas_aud.empty: total_erros += len(df_vendas_aud[df_vendas_aud['Validação TIPI'].str.contains("Ausente")])
        c4.metric("Alertas TIPI", total_erros, delta="Atenção" if total_erros > 0 else "OK", delta_color="inverse")
        
        st.divider()
        if not df_vendas_aud.empty:
            st.markdown("#### Composição da Carga (Saídas)")
            total_ibs = df_vendas_aud['vIBS'].sum()
            total_cbs = df_vendas_aud['vCBS'].sum()
            st.bar_chart(pd.DataFrame({'Imposto': ['IBS', 'CBS'], 'Valor': [total_ibs, total_cbs]}), x='Imposto', y='Valor', color="#E67E22")

    col_config = {
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "vICMS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vPIS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vCOFINS": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
        "vIBS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vCBS": st.column_config.NumberColumn(format="R$ %.2f"),
        "Novo CST": st.column_config.TextColumn("Novo CST", width="small"),
        "DescRegra": st.column_config.TextColumn("Regra Fiscal", width="large"),
        "Validação TIPI": st.column_config.TextColumn("TIPI", width="small"),
    }

    with tabs[1]:
        if not df_vendas_aud.empty: st.dataframe(preparar_exibicao(df_vendas_aud), use_container_width=True, hide_index=True, column_config=col_config)
    with tabs[2]:
        if not df_compras_aud.empty: st.dataframe(preparar_exibicao(df_compras_aud), use_container_width=True, hide_index=True, column_config=col_config)
    with tabs[3]:
        c1, c2 = st.columns(2)
        if not df_vendas_aud.empty: c1.dataframe(df_vendas_aud[['Chave NFe']].drop_duplicates(), use_container_width=True)
        if not df_compras_aud.empty: c2.dataframe(df_compras_aud[['Chave NFe']].drop_duplicates(), use_container_width=True)

    st.markdown("---")
    st.markdown("### 📥 Exportar Resultados")
    
    c_pdf, c_xls = st.columns(2)
    
    with c_pdf:
        if not df_vendas_aud.empty or not df_compras_aud.empty:
            try:
                pdf_bytes = relatorio.gerar_pdf_bytes(st.session_state.empresa_nome, df_vendas_aud, df_compras_aud)
                st.download_button("📄 BAIXAR LAUDO EM PDF", pdf_bytes, "Laudo_Auditoria.pdf", "application/pdf", use_container_width=True)
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
                
    with c_xls:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            if not df_vendas_aud.empty: preparar_exibicao(df_vendas_aud).to_excel(writer, index=False, sheet_name="Auditoria_Vendas")
            if not df_compras_aud.empty: preparar_exibicao(df_compras_aud).to_excel(writer, index=False, sheet_name="Auditoria_Compras")
            if not df_estoque_aud.empty: df_estoque_aud.to_excel(writer, index=False, sheet_name="Auditoria_SPED")
        st.download_button("📊 BAIXAR PLANILHA EXCEL", buffer, "Dados_Auditoria.xlsx", "primary", use_container_width=True)

else:
    st.info("👈 Aguardando arquivos...")