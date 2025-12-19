import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - LCP 214",
    page_icon="⚖️",
    layout="wide"
)

# Estilo Profissional
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #0e1117;}
    .stMetric {background-color: #fff; padding: 15px; border-radius: 10px; border-left: 5px solid #28B463;}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal Inteligente")
st.caption("Versão 9.0: Mapeamento Completo dos Anexos (I ao XV)")
st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS (CORRIGIDA COM SEU TEXTO) ---
# Agora reflete a estrutura real da LCP 214
CONFIG_ANEXOS = {
    "ANEXO I": {
        "Descricao": "Cesta Básica Nacional (Alíquota Zero)",
        "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)",
        "Capitulos_Permitidos": ["02", "03", "04", "07", "08", "09", "10", "11", "12", "15", "16", "17", "18", "19", "20", "21", "23", "25"]
    },
    "ANEXO IV": {
        "Descricao": "Dispositivos Médicos (Redução 60%)",
        "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)",
        "Capitulos_Permitidos": ["30", "37", "39", "40", "84", "90", "94"]
    },
    "ANEXO VII": {
        "Descricao": "Alimentos Reduzidos (Redução 60%)",
        "cClassTrib": "200003", "CST": "20", "Status": "REDUZIDA 60% (Anexo VII)",
        "Capitulos_Permitidos": ["03", "04", "07", "08", "10", "11", "12", "15", "16", "19", "20", "21", "22"]
    },
    "ANEXO VIII": {
        "Descricao": "Higiene Pessoal e Limpeza (Redução 60%)",
        "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo VIII)",
        "Capitulos_Permitidos": ["33", "34", "38", "48", "96"] # Só aceita cosméticos, sabão, papel e fraldas
    },
    "ANEXO XII": {
        "Descricao": "Dispositivos Médicos (Alíquota Zero)",
        "cClassTrib": "200005", "CST": "40", "Status": "ZERO (Anexo XII)",
        "Capitulos_Permitidos": ["90"]
    },
    "ANEXO XIV": {
        "Descricao": "Medicamentos (Alíquota Zero)",
        "cClassTrib": "200009", "CST": "40", "Status": "ZERO (Anexo XIV)",
        "Capitulos_Permitidos": ["28", "29", "30"]
    },
    "ANEXO XV": {
        "Descricao": "Hortifruti e Ovos (Redução 100%)",
        "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo XV)",
        "Capitulos_Permitidos": ["04", "06", "07", "08"]
    }
}

# --- 3. TRAVAS DE SEGURANÇA ---
def verificar_imposto_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    # 22=Bebidas, 24=Fumo, 87=Veículos, 93=Armas
    # Exceção: 2202 (Refrigerante/Água) às vezes entra em anexo VII, mas cuidado.
    # Vamos bloquear tabaco e álcool forte.
    proibidos = ['2203', '2204', '2205', '2206', '2207', '2208', '24', '87', '93']
    if any(ncm.startswith(p) for p in proibidos):
        return True
    return False

# --- 4. LEITURA ONLINE INTELIGENTE ---
@st.cache_data
def carregar_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            return df
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def mapear_anexos_online():
    url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    headers = {"User-Agent": "Mozilla/5.0"}
    mapa_ncm_anexo = {}
    
    try:
        response = requests.get(url, headers=headers, timeout=25)
        soup = BeautifulSoup(response.content, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        texto = soup.get_text(separator=' ').replace('\n', ' ')
        texto = re.sub(r'\s+', ' ', texto)
        
        # Encontra posições dos Anexos no texto
        anexos_pos = []
        for anexo in CONFIG_ANEXOS.keys():
            pos = texto.upper().find(anexo)
            # Se achou no site, guarda a posição
            if pos != -1: anexos_pos.append((pos, anexo))
        
        anexos_pos.sort()
        
        # Leitura por Bloco
        for i in range(len(anexos_pos)):
            nome_anexo = anexos_pos[i][1]
            inicio = anexos_pos[i][0]
            
            # Fim é o próximo anexo ou o fim do texto
            if i + 1 < len(anexos_pos):
                fim = anexos_pos[i+1][0]
            else:
                fim = len(texto)
            
            bloco = texto[inicio:fim].replace('.', '')
            
            # Extrai códigos
            ncms = re.findall(r'\b\d{8}\b', bloco)
            caps = re.findall(r'\b\d{4}\b', bloco)
            
            # Filtro de Segurança
            capitulos_aceitos = CONFIG_ANEXOS[nome_anexo]["Capitulos_Permitidos"]
            
            for n in ncms:
                if any(n.startswith(c) for c in capitulos_aceitos):
                    mapa_ncm_anexo[n] = nome_anexo
                    
            for c in caps: 
                if c not in mapa_ncm_anexo: 
                    if any(c.startswith(cap_ok) for cap_ok in capitulos_aceitos):
                        mapa_ncm_anexo[c] = nome_anexo
                    
        return mapa_ncm_anexo
    except: return {}

# --- 5. CLASSIFICAÇÃO CENTRAL ---

def classificar_item_master(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm_limpo = str(ncm).replace('.', '')
    cfop_limpo = str(cfop).replace('.', '')
    
    cClassTrib, desc, cst, status, origem = '000001', 'Padrão - Tributação Integral', '01', 'PADRAO', 'Regra Geral'
    
    # 1. TRAVA DE SEGURANÇA (Imposto Seletivo)
    if verificar_imposto_seletivo(ncm_limpo):
        return '000001', 'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava de Segurança'

    # 2. BUSCA NO MAPA DA LEI (Prioridade)
    anexo_encontrado = None
    if ncm_limpo in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo]
    elif ncm_limpo[:4] in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
    
    # 3. APLICA REGRA (Se não for exportação)
    if cfop_limpo.startswith('7'):
        return '410004', 'Exportação', 'IMUNE', '50', 'Não'
        
    elif anexo_encontrado:
        regra = CONFIG_ANEXOS[anexo_encontrado]
        return regra['cClassTrib'], f"{regra['Descricao']} (Via {anexo_encontrado})", regra['Status'], regra['CST'], anexo_encontrado
    
    # 4. FALLBACK JSON (Se não achou na lei)
    else:
        # Busca inteligente por texto
        termo_busca = ""
        if ncm_limpo.startswith('30'): termo_busca = "medicamentos"
        elif ncm_limpo.startswith('1006'): termo_busca = "cesta básica"
        elif ncm_limpo.startswith('04'): termo_busca = "cesta básica" # Leite/Queijo
        else: termo_busca = "tributação integral"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return cClassTrib, desc, status, cst, origem

# --- 6. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=50)
    st.subheader("Auditoria Fiscal")
    uploaded_files = st.file_uploader("XMLs de Venda", type=['xml'], accept_multiple_files=True)
    
    st.markdown("---")
    with st.spinner("Atualizando base legal..."):
        mapa_anexos = mapear_anexos_online()
    if mapa_anexos: 
        st.success(f"🟢 Planalto Conectado")
        st.caption(f"{len(mapa_anexos)} regras de NCM carregadas.")

if uploaded_files:
    if df_regras.empty: st.warning("Aviso: JSON de regras não carregado.")
    
    lista_produtos = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    
    # Barra de progresso
    progresso = st.progress(0)
    
    for i, arquivo in enumerate(uploaded_files):
        try:
            tree = ET.parse(arquivo)
            root = tree.getroot()
            chave = root.find('.//ns:infNFe', ns).attrib.get('Id', '')[3:]
            for item in root.findall('.//ns:det', ns):
                prod = item.find('ns:prod', ns)
                lista_produtos.append({
                    'Chave NFe': chave,
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Valor': float(prod.find('ns:vProd', ns).text)
                })
        except: continue
        progresso.progress((i + 1) / len(uploaded_files))
    
    df_base = pd.DataFrame(lista_produtos)
    
    if not df_base.empty:
        df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
        
        resultados = df_analise.apply(
            lambda row: classificar_item_master(row['NCM'], row['CFOP'], row['Produto'], df_regras, mapa_anexos), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'CST', 'Origem Legal']] = resultados
        
        # --- DASHBOARD ---
        st.markdown("### 📊 Resultado da Análise")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Itens", len(df_analise))
        c2.metric("Base Legal", len(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")]))
        c3.metric("Cesta Básica/Zero", len(df_analise[df_analise['Status'].str.contains("ZERO")]))
        c4.metric("Seletivo (Alerta)", len(df_analise[df_analise['Status'] == 'ALERTA SELETIVO']), delta_color="inverse")
        
        # TABS
        tab1, tab2, tab3 = st.tabs(["📋 Geral", "🔎 Por Anexo", "⚠️ Alertas"])
        
        with tab1: st.dataframe(df_analise, use_container_width=True)
        
        with tab2:
            anexo_filter = st.selectbox("Selecione o Anexo:", ["ANEXO I", "ANEXO IV", "ANEXO VII", "ANEXO VIII", "ANEXO XIV", "ANEXO XV"])
            st.dataframe(df_analise[df_analise['Origem Legal'] == anexo_filter], use_container_width=True)
            
        with tab3:
            st.dataframe(df_analise[df_analise['Status'] == 'ALERTA SELETIVO'], use_container_width=True)
        
        # EXCEL
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False, sheet_name='Geral')
            df_analise[df_analise['Origem Legal'].str.contains("ANEXO")].to_excel(writer, index=False, sheet_name='Base Legal')
            df_analise[df_analise['Status'] == 'ALERTA SELETIVO'].to_excel(writer, index=False, sheet_name='Alertas')
        
        st.download_button("📥 Baixar Planilha Oficial (.xlsx)", buffer, "Auditoria_Final.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")