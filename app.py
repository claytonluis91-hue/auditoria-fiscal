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
    initial_sidebar_state="collapsed"
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

# --- CSS PROFISSIONAL ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .stApp { background-color: #F8F9FA; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }
    
    /* SIDEBAR */
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E0E0E0; }
    section[data-testid="stSidebar"] * { color: #2C3E50 !important; }
    
    /* HEADER */
    .main-header { font-size: 2.5rem; font-weight: 800; color: #1a252f; text-align: center; margin-top: 20px;}
    .sub-header { font-size: 1.1rem; color: #7F8C8D; text-align: center; margin-bottom: 30px; }
    .company-badge { 
        background-color: #E67E22; color: white; padding: 5px 20px; border-radius: 20px; 
        font-weight: bold; font-size: 1rem; display: block; margin: 0 auto 20px auto; width: fit-content;
    }

    /* UPLOAD CARDS */
    .upload-title { font-weight: 700; color: #2C3E50; margin-bottom: 5px; font-size: 1.1rem; }
    .upload-desc { font-size: 0.85rem; color: #7F8C8D; margin-bottom: 10px; }

    /* METRICS */
    div[data-testid="stMetric"] { 
        background-color: #FFFFFF !important; border: 1px solid #E0E0E0; border-radius: 12px; 
        padding: 15px; border-left: 6px solid #E67E22; 
    }
    div[data-testid="stMetricLabel"] p { color: #7F8C8D !important; }
    div[data-testid="stMetricValue"] div { color: #2C3E50 !important; }

    /* BOTÕES */
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

# --- BARRA LATERAL ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=50)
    st.markdown("### ⚙️ Configurações")
    aliquota_input = st.number_input("Alíquota IBS/CBS (%)", 0.0, 100.0, 26.5, 0.5)
    
    st.divider()
    with st.expander("Atualizar TIPI / Regras"):
        uploaded_tipi = st.file_uploader("Arquivo TIPI (.xlsx)", type=['xlsx', 'csv'])
        if st.button("Recarregar Motor"):
            carregar_bases.clear()
            st.rerun()
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR TUDO", type="secondary"):
        reset_all()
        st.rerun()

    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- CORPO PRINCIPAL ---
st.markdown('<div class="main-header">cClass Auditor AI</div>', unsafe_allow_html=True)
if st.session_state.empresa_nome != "Nenhuma Empresa":
    st.markdown(f'<div class="company-badge">🏢 {st.session_state.empresa_nome}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sub-header">Auditoria Fiscal e Planejamento Tributário</div>', unsafe_allow_html=True)

modo_selecionado = st.radio("Origem dos Dados:", ["📄 XML (Notas Fiscais)", "📝 SPED Fiscal (TXT)"], horizontal=True, label_visibility="collapsed")
st.markdown("---")

ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

# === UPLOADS ===
if modo_selecionado == "📄 XML (Notas Fiscais)":
    if not st.session_state.estoque_df.empty: 
        st.session_state.estoque_df = pd.DataFrame()
        st.toast("Modo XML ativado. SPED limpo.", icon="🔄")

    c_venda, c_compra = st.columns(2)
    with c_venda:
        st.markdown('<div class="upload-title">📤 VENDAS (Saídas)</div>', unsafe_allow_html=True)
        vendas_files = st.file_uploader("Upload Vendas", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}", label_visibility="collapsed")
    with c_compra:
        st.markdown('<div class="upload-title">📥 COMPRAS (Entradas)</div>', unsafe_allow_html=True)
        compras_files = st.file_uploader("Upload Compras", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}", label_visibility="collapsed")

    def processar_arquivos(arquivos, tipo):
        lista = []
        for arquivo in arquivos:
            try:
                tree = ET.parse(arquivo)
                if tipo == 'SAIDA' and st.session_state.empresa_nome == "Nenhuma Empresa":
                    st.session_state.empresa_nome = motor.extrair_nome_empresa_xml(tree, ns)
                lista.extend(motor.processar_xml_detalhado(tree, ns, tipo))
            except: continue
        return lista

    if vendas_files and st.session_state.vendas_df.empty:
        with st.spinner("Lendo Vendas..."):
            st.session_state.vendas_df = pd.DataFrame(processar_arquivos(vendas_files, 'SAIDA'))
            st.rerun()

    if compras_files and st.session_state.compras_df.empty:
        with st.spinner("Lendo Compras..."):
            st.session_state.compras_df = pd.DataFrame(processar_arquivos(compras_files, 'ENTRADA'))
            st.rerun()

else:
    if not st.session_state.vendas_df.empty or not st.session_state.compras_df.empty:
        st.session_state.vendas_df = pd.DataFrame()
        st.session_state.compras_df = pd.DataFrame()
        st.toast("Modo SPED ativado. XMLs limpos.", icon="🔄")

    st.markdown('<div class="upload-title" style="text-align:center;">📝 ARQUIVO SPED FISCAL</div>', unsafe_allow_html=True)
    col_sped = st.columns([1, 2, 1])
    with col_sped[1]:
        sped_file = st.file_uploader("Upload SPED", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}", label_visibility="collapsed")

    if sped_file and st.session_state.estoque_df.empty:
        with st.spinner("Lendo SPED..."):
            nome, itens = motor.processar_sped_fiscal(sped_file)
            st.session_state.empresa_nome = nome
            st.session_state.estoque_df = pd.DataFrame(itens)
            st.rerun()

# --- MOTOR DE AUDITORIA ---
def auditar_df(df, aliquota):
    if df.empty: return df
    res = df.apply(
        lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliquota), 
        axis=1, result_type='expand'
    )
    df[['cClassTrib', 'DescRegra', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada']] = res
    return df

df_vendas_aud = auditar_df(st.session_state.vendas_df.copy(), aliquota_input/100)
df_compras_aud = auditar_df(st.session_state.compras_df.copy(), aliquota_input/100)
df_estoque_aud = auditar_df(st.session_state.estoque_df.copy(), aliquota_input/100)

# --- VISUALIZAÇÃO ---
tem_dados = not df_vendas_aud.empty or not df_compras_aud.empty or not df_estoque_aud.empty

if tem_dados:
    # Definição das Colunas conforme solicitado
    cols_ordenadas = [
        'Cód. Produto', 'Descrição Produto', 'NCM', 'CFOP', 'Novo CST', 'cClassTrib', 
        'DescRegra', 'Origem Legal', 'Valor', 'vICMS', 'vPIS', 'vCOFINS', 
        'Carga Atual', 'Carga Projetada', 'Validação TIPI'
    ]
    
    # Prepara DF para exibição (Renomeando 'Produto' para 'Descrição Produto' para bater com seu pedido)
    def preparar_exibicao(df):
        if df.empty: return df
        df_view = df.rename(columns={'Produto': 'Descrição Produto'})
        # Garante que as colunas existem (vICMS etc vem do motor)
        return df_view[cols_ordenadas]

    # --- ABAS ---
    tabs = st.tabs(["📊 Resumo Executivo", "📤 Saídas (Vendas)", "📥 Entradas (Compras)", "📂 Arquivos Processados"])

    # 1. ABA RESUMO (DASHBOARD)
    with tabs[0]:
        st.markdown("### Visão Geral da Apuração")
        
        # Totais
        debito = df_vendas_aud['Carga Projetada'].sum() if not df_vendas_aud.empty else 0
        credito = df_compras_aud['Carga Projetada'].sum() if not df_compras_aud.empty else 0
        saldo = debito - credito
        
        # Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Débitos (Saídas)", f"R$ {debito:,.2f}", delta="Passivo", delta_color="inverse")
        st.markdown("""<style>div[data-testid="metric-container"]:nth-child(2) {border-left: 6px solid #27AE60 !important;}</style>""", unsafe_allow_html=True)
        c2.metric("Créditos (Entradas)", f"R$ {credito:,.2f}", delta="Ativo", delta_color="normal")
        c3.metric("Saldo Estimado", f"R$ {abs(saldo):,.2f}", delta="Pagar" if saldo > 0 else "Credor", delta_color="inverse")
        
        # Auditoria (Erros)
        total_erros = 0
        if not df_vendas_aud.empty: total_erros += len(df_vendas_aud[df_vendas_aud['Validação TIPI'].str.contains("Ausente")])
        c4.metric("Alertas TIPI", total_erros, delta="Atenção" if total_erros > 0 else "OK", delta_color="inverse")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("#### Distribuição da Carga (Saídas)")
            if not df_vendas_aud.empty:
                st.bar_chart(df_vendas_aud['Status'].value_counts(), color="#E67E22")
            else: st.info("Sem dados de saída.")
            
        with g2:
            st.markdown("#### Impacto por Classificação")
            if not df_vendas_aud.empty:
                resumo_impacto = df_vendas_aud.groupby('Status')[['Carga Atual', 'Carga Projetada']].sum()
                st.bar_chart(resumo_impacto)

    # Configuração de Colunas para as Tabelas
    col_config = {
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "vICMS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vPIS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vCOFINS": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
        "Novo CST": st.column_config.TextColumn("Novo CST", width="small"),
        "DescRegra": st.column_config.TextColumn("Regra Fiscal", width="large"),
        "Validação TIPI": st.column_config.TextColumn("TIPI", width="small"),
    }

    # 2. ABA VENDAS
    with tabs[1]:
        if not df_vendas_aud.empty:
            df_view_v = preparar_exibicao(df_vendas_aud)
            st.dataframe(df_view_v, use_container_width=True, hide_index=True, column_config=col_config)
        else: st.info("Nenhuma venda carregada.")

    # 3. ABA COMPRAS
    with tabs[2]:
        if not df_compras_aud.empty:
            df_view_c = preparar_exibicao(df_compras_aud)
            st.dataframe(df_view_c, use_container_width=True, hide_index=True, column_config=col_config)
        else: st.info("Nenhuma compra carregada.")

    # 4. ABA ARQUIVOS (Chaves NFe)
    with tabs[3]:
        c_arq1, c_arq2 = st.columns(2)
        with c_arq1:
            st.markdown("#### 📄 Arquivos de Saída")
            if not df_vendas_aud.empty:
                st.dataframe(df_vendas_aud[['Chave NFe']].drop_duplicates(), use_container_width=True, hide_index=True)
        with c_arq2:
            st.markdown("#### 📄 Arquivos de Entrada")
            if not df_compras_aud.empty:
                st.dataframe(df_compras_aud[['Chave NFe']].drop_duplicates(), use_container_width=True, hide_index=True)

    # DOWNLOAD GLOBAL
    st.markdown("---")
    st.markdown("### 📥 Exportar Laudo")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        if not df_vendas_aud.empty: 
            preparar_exibicao(df_vendas_aud).to_excel(writer, index=False, sheet_name="Auditoria_Vendas")
        if not df_compras_aud.empty: 
            preparar_exibicao(df_compras_aud).to_excel(writer, index=False, sheet_name="Auditoria_Compras")
        if not df_estoque_aud.empty: 
            df_estoque_aud.to_excel(writer, index=False, sheet_name="Auditoria_SPED")
            
    st.download_button("BAIXAR RELATÓRIO COMPLETO (.XLSX)", buffer, "Laudo_Auditoria_Nascel.xlsx", "primary", use_container_width=True)

else:
    st.info("👈 Aguardando arquivos...")