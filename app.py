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
    initial_sidebar_state="collapsed" # Barra lateral começa fechada para dar foco ao centro
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
    # st.rerun() # O rerun acontece pelo botão

# --- CSS PROFISSIONAL (CENTRALIZADO) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* GERAL */
    .stApp { background-color: #F8F9FA; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }
    
    /* BARRA LATERAL (Clean) */
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E0E0E0; }
    section[data-testid="stSidebar"] * { color: #2C3E50 !important; }
    
    /* HEADER */
    .main-header { font-size: 2.5rem; font-weight: 800; color: #1a252f; text-align: center; margin-top: 20px;}
    .sub-header { font-size: 1.1rem; color: #7F8C8D; text-align: center; margin-bottom: 30px; }
    .company-badge { 
        background-color: #E67E22; color: white; padding: 5px 20px; border-radius: 20px; 
        font-weight: bold; font-size: 1rem; display: block; margin: 0 auto 20px auto; width: fit-content;
    }

    /* ÁREA DE UPLOAD (CARDS CENTRAIS) */
    .upload-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #E0E0E0;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        text-align: center;
        height: 100%;
    }
    .upload-title {
        font-weight: 700;
        color: #2C3E50;
        margin-bottom: 10px;
        font-size: 1.1rem;
    }
    .upload-desc {
        font-size: 0.85rem;
        color: #7F8C8D;
        margin-bottom: 15px;
    }

    /* DASHBOARD METRICS */
    div[data-testid="stMetric"] { 
        background-color: #FFFFFF !important; border: 1px solid #E0E0E0; border-radius: 12px; 
        padding: 15px; border-left: 6px solid #E67E22; 
    }
    div[data-testid="stMetricLabel"] p { color: #7F8C8D !important; }
    div[data-testid="stMetricValue"] div { color: #2C3E50 !important; }

    /* BOTÕES */
    div.stButton > button[kind="primary"] { background-color: #E67E22 !important; color: white !important; width: 100%; }
    div.stButton > button[kind="secondary"] { background-color: #ECF0F1 !important; color: #2C3E50 !important; width: 100%; border: 1px solid #BDC3C7 !important;}
    
    /* RADIO BUTTON CUSTOMIZADO */
    div[role="radiogroup"] {
        display: flex;
        justify-content: center;
        gap: 20px;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CACHE ---
@st.cache_data
def carregar_bases():
    return motor.carregar_base_legal(), motor.carregar_json_regras()

@st.cache_data
def carregar_tipi_cache(file):
    return motor.carregar_tipi(file)

# --- BARRA LATERAL (APENAS PARAMETROS) ---
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

    # Carregamento silencioso
    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- CORPO PRINCIPAL ---

# 1. Cabeçalho
st.markdown('<div class="main-header">cClass Auditor AI</div>', unsafe_allow_html=True)
if st.session_state.empresa_nome != "Nenhuma Empresa":
    st.markdown(f'<div class="company-badge">🏢 {st.session_state.empresa_nome}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sub-header">Selecione o método de importação abaixo para iniciar</div>', unsafe_allow_html=True)

# 2. Seletor de Modo (Exclusividade)
modo_selecionado = st.radio(
    "Escolha a Origem dos Dados:",
    ["📄 XML (Notas Fiscais)", "📝 SPED Fiscal (TXT)"],
    horizontal=True,
    label_visibility="collapsed"
)

# 3. Áreas de Upload (Condicionais)
st.markdown("---")

ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

# === MODO XML ===
if modo_selecionado == "📄 XML (Notas Fiscais)":
    # Se mudar de modo, limpa o SPED da memória para não misturar
    if not st.session_state.estoque_df.empty: 
        st.session_state.estoque_df = pd.DataFrame()
        st.toast("Modo alterado: Dados do SPED foram limpos.", icon="🔄")

    c_venda, c_compra = st.columns(2)
    
    with c_venda:
        st.markdown('<div class="upload-title">📤 VENDAS (Saídas)</div>', unsafe_allow_html=True)
        st.markdown('<div class="upload-desc">Arraste os XMLs de emissão própria.<br><b>Gera Auditoria de Débitos.</b></div>', unsafe_allow_html=True)
        vendas_files = st.file_uploader("Upload Vendas", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}", label_visibility="collapsed")
        
    with c_compra:
        st.markdown('<div class="upload-title">📥 COMPRAS (Entradas)</div>', unsafe_allow_html=True)
        st.markdown('<div class="upload-desc">Arraste os XMLs de fornecedores.<br><b>Ativa Simulação de Créditos.</b></div>', unsafe_allow_html=True)
        compras_files = st.file_uploader("Upload Compras", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}", label_visibility="collapsed")

    # Processamento XML
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

# === MODO SPED ===
else:
    # Se mudar de modo, limpa os XMLs da memória
    if not st.session_state.vendas_df.empty or not st.session_state.compras_df.empty:
        st.session_state.vendas_df = pd.DataFrame()
        st.session_state.compras_df = pd.DataFrame()
        st.toast("Modo alterado: Dados de XML foram limpos.", icon="🔄")

    st.markdown('<div class="upload-title">📝 ARQUIVO SPED FISCAL</div>', unsafe_allow_html=True)
    st.markdown('<div class="upload-desc" style="text-align:center;">Carregue o arquivo TXT integral.<br><b>Auditoria Completa de Cadastro (0200).</b></div>', unsafe_allow_html=True)
    
    col_sped_centrada = st.columns([1, 2, 1])
    with col_sped_centrada[1]:
        sped_file = st.file_uploader("Upload SPED", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}", label_visibility="collapsed")

    if sped_file and st.session_state.estoque_df.empty:
        with st.spinner("Lendo SPED Fiscal..."):
            nome, itens = motor.processar_sped_fiscal(sped_file)
            st.session_state.empresa_nome = nome
            st.session_state.estoque_df = pd.DataFrame(itens)
            st.rerun()


# --- MOTOR DE AUDITORIA (COMUM) ---
def auditar_df(df, aliquota):
    if df.empty: return df
    res = df.apply(
        lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliquota), 
        axis=1, result_type='expand'
    )
    df[['cClassTrib', 'Descrição', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada']] = res
    return df

# Audita o que tiver na memória
df_vendas_aud = auditar_df(st.session_state.vendas_df.copy(), aliquota_input/100)
df_compras_aud = auditar_df(st.session_state.compras_df.copy(), aliquota_input/100)
df_estoque_aud = auditar_df(st.session_state.estoque_df.copy(), aliquota_input/100)

# --- VISUALIZAÇÃO DE RESULTADOS ---
tem_dados = not df_vendas_aud.empty or not df_compras_aud.empty or not df_estoque_aud.empty

if tem_dados:
    st.markdown("---")
    st.markdown("### 📊 Resultado da Análise")

    # Configuração Visual das Tabelas
    col_config = {
        "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
        "Status": st.column_config.TextColumn("Regra Aplicada", width="medium"),
        "Novo CST": st.column_config.TextColumn("Novo CST", width="small"),
        "cClassTrib": st.column_config.TextColumn("Class. Trib.", width="medium"),
        "Validação TIPI": st.column_config.TextColumn("TIPI", width="small")
    }

    # === VISÃO SPED ===
    if modo_selecionado == "📝 SPED Fiscal (TXT)":
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens Cadastrados", len(df_estoque_aud))
        c2.metric("Itens com Benefício", len(df_estoque_aud[df_estoque_aud['Origem Legal'].str.contains("Anexo")]))
        
        erros = len(df_estoque_aud[df_estoque_aud['Validação TIPI'].str.contains("Ausente")])
        c3.metric("Erros NCM (TIPI)", erros, delta="Corrigir" if erros > 0 else "OK", delta_color="inverse")
        
        st.dataframe(df_estoque_aud, use_container_width=True, hide_index=True, column_config=col_config)
        
        # Download SPED
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_estoque_aud.to_excel(writer, index=False, sheet_name="Auditoria_SPED")
        st.download_button("📥 BAIXAR RELATÓRIO SPED", buffer, "Auditoria_SPED.xlsx", "primary", use_container_width=True)

    # === VISÃO XML (Vendas e/ou Compras) ===
    else:
        # Só exibe painel de apuração se tiver VENDAS e COMPRAS
        if not df_vendas_aud.empty and not df_compras_aud.empty:
            debito = df_vendas_aud['Carga Projetada'].sum()
            credito = df_compras_aud['Carga Projetada'].sum()
            saldo = debito - credito
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Débitos (Saídas)", f"R$ {debito:,.2f}", delta="IBS/CBS Devido", delta_color="inverse")
            st.markdown("""<style>div[data-testid="metric-container"]:nth-child(2) {border-left: 6px solid #27AE60 !important;}</style>""", unsafe_allow_html=True)
            k2.metric("Créditos (Entradas)", f"R$ {credito:,.2f}", delta="Recuperável", delta_color="normal")
            k3.metric("Saldo a Pagar", f"R$ {abs(saldo):,.2f}", delta="Pagar" if saldo > 0 else "Credor", delta_color="inverse")
            
            base = df_vendas_aud['Valor'].sum()
            aliq_efetiva = (saldo / base * 100) if base > 0 else 0
            k4.metric("Alíquota Efetiva", f"{aliq_efetiva:.2f}%")
        
        elif not df_vendas_aud.empty:
            # Só Vendas carregadas
            debito = df_vendas_aud['Carga Projetada'].sum()
            k1, k2 = st.columns(2)
            k1.metric("Total Auditado (vProd)", f"R$ {df_vendas_aud['Valor'].sum():,.2f}")
            k2.metric("Débitos Projetados", f"R$ {debito:,.2f}")
            st.info("💡 DICA: Carregue os XMLs de Entrada (lado direito) para ver o cálculo da Não-Cumulatividade (Créditos).")

        # Abas
        tab_v, tab_c = st.tabs(["📤 Saídas (Vendas)", "📥 Entradas (Compras)"])
        with tab_v:
            if not df_vendas_aud.empty:
                st.dataframe(df_vendas_aud, use_container_width=True, hide_index=True, column_config=col_config)
            else: st.warning("Aguardando XMLs de Venda...")
            
        with tab_c:
            if not df_compras_aud.empty:
                st.dataframe(df_compras_aud, use_container_width=True, hide_index=True, column_config=col_config)
            else: 
                if modo_selecionado == "📄 XML (Notas Fiscais)":
                    st.info("Nenhum XML de compra carregado. A simulação considera apenas os débitos.")

        # Download XML
        if not df_vendas_aud.empty or not df_compras_aud.empty:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                if not df_vendas_aud.empty: df_vendas_aud.to_excel(writer, index=False, sheet_name="Vendas")
                if not df_compras_aud.empty: df_compras_aud.to_excel(writer, index=False, sheet_name="Compras")
            st.download_button("📥 BAIXAR RELATÓRIO XML", buffer, "Auditoria_XML.xlsx", "primary", use_container_width=True)

else:
    # Estado vazio (Hero)
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.info("👈 Utilize os botões acima para carregar seus arquivos.")