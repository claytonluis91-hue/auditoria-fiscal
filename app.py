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

# Estilos CSS
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #0e1117;}
    .stMetric {background-color: #fff; padding: 15px; border-radius: 10px; border-left: 5px solid #2E86C1;}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal Inteligente")
st.caption("Versão 8.0: Filtros de Capítulos e Ajuste de Nomenclatura")
st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS (COM FILTROS) ---
# Aqui você me ajuda! Definimos quais capítulos (2 primeiros dígitos do NCM)
# são aceitáveis para cada anexo. Isso evita que Queijo (04) caia em Higiene.
CONFIG_ANEXOS = {
    "ANEXO I": {
        "Descricao": "Cesta Básica Nacional (Alíquota Zero)",
        "cClassTrib": "200003", 
        "CST": "40", 
        "Status": "ZERO (Anexo I)",
        # Aceita quase tudo de comida, mas bloqueia coisas estranhas
        "Capitulos_Permitidos": ["02", "03", "04", "07", "08", "09", "10", "11", "12", "15", "16", "17", "18", "19", "20", "21", "23", "25", "30", "33"]
    },
    "ANEXO II": {
        "Descricao": "Medicamentos (Redução 60%)",
        "cClassTrib": "200009", 
        "CST": "20", 
        "Status": "REDUZIDA 60% (Anexo II)",
        "Capitulos_Permitidos": ["30"] # Só aceita capítulo 30
    },
    "ANEXO III": {
        "Descricao": "Dispositivos Médicos (Redução 60%)",
        "cClassTrib": "200005", 
        "CST": "20", 
        "Status": "REDUZIDA 60% (Anexo III)",
        "Capitulos_Permitidos": ["30", "90", "94"] # Médicos e equipamentos
    },
    "ANEXO IV": {
        "Descricao": "Produtos de Higiene (Redução 60%)",
        "cClassTrib": "200035", 
        "CST": "20", 
        "Status": "REDUZIDA 60% (Anexo IV)",
        "Capitulos_Permitidos": ["33", "34", "96"] # Só aceita Cosméticos, Sabões e Higiene
    }
}

# --- 3. TRAVAS DE SEGURANÇA (IMPOSTO SELETIVO) ---
def verificar_imposto_seletivo(ncm):
    """
    Retorna True se for um produto perigoso (Bebida, Cigarro, Veículo, Arma).
    """
    ncm = str(ncm).replace('.', '')
    proibidos = ['22', '24', '87', '93'] # Bebidas, Fumo, Veículos, Armas
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
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.content, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        texto = soup.get_text(separator=' ').replace('\n', ' ')
        texto = re.sub(r'\s+', ' ', texto)
        
        # Encontra posições dos Anexos
        anexos_pos = []
        for anexo in CONFIG_ANEXOS.keys():
            pos = texto.upper().find(anexo)
            if pos != -1: anexos_pos.append((pos, anexo))
        anexos_pos.sort()
        
        # Define um ponto de parada para não ler lixo no final
        pos_fim = texto.upper().find("IMPOSTO SELETIVO")
        if pos_fim == -1: pos_fim = len(texto)

        for i in range(len(anexos_pos)):
            nome_anexo = anexos_pos[i][1]
            inicio = anexos_pos[i][0]
            
            # O fim é o começo do próximo anexo ou o ponto de parada
            if i + 1 < len(anexos_pos):
                fim = anexos_pos[i+1][0]
            else:
                fim = pos_fim
            
            bloco = texto[inicio:fim].replace('.', '')
            
            # Extrai NCMs e Capítulos
            ncms = re.findall(r'\b\d{8}\b', bloco)
            caps = re.findall(r'\b\d{4}\b', bloco)
            
            # --- FILTRAGEM DE CAPÍTULOS (AQUI EVITA O QUEIJO NO ANEXO IV) ---
            capitulos_aceitos = CONFIG_ANEXOS[nome_anexo]["Capitulos_Permitidos"]
            
            for n in ncms:
                # Só adiciona se o NCM começar com os capítulos permitidos daquele anexo
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
    
    # 1. VERIFICA SE É IMPOSTO SELETIVO (Prioridade Máxima de Alerta)
    if verificar_imposto_seletivo(ncm_limpo):
        # Texto exato solicitado
        return '000001', 'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava de Segurança'

    # 2. VERIFICA NOS ANEXOS DA LEI
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
        termo_busca = ""
        if ncm_limpo.startswith('30'): termo_busca = "medicamentos"
        elif ncm_limpo.startswith('1006'): termo_busca = "cesta básica"
        else: termo_busca = "tributação integral"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return cClassTrib, desc, status, cst, origem

# --- 6. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.subheader("Painel de Controle")
    uploaded_files = st.file_uploader("Carregar XMLs", type=['xml'], accept_multiple_files=True)
    with st.spinner("Atualizando Lei..."):
        mapa_anexos = mapear_anexos_online()
    if mapa_anexos: st.success(f"🟢 Lei Mapeada ({len(mapa_anexos)} regras)")

if uploaded_files:
    if df_regras.empty: st.warning("Sem JSON de regras.")
    
    lista_produtos = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    
    for arquivo in uploaded_files:
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
    
    df_base = pd.DataFrame(lista_produtos)
    
    if not df_base.empty:
        df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
        
        resultados = df_analise.apply(
            lambda row: classificar_item_master(row['NCM'], row['CFOP'], row['Produto'], df_regras, mapa_anexos), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'CST', 'Origem Legal']] = resultados
        
        st.markdown("### 📊 Auditoria Fiscal")
        col1, col2 = st.columns(2)
        col1.metric("Produtos Analisados", len(df_analise))
        col2.metric("Itens de Imposto Seletivo", len(df_analise[df_analise['Status'] == 'ALERTA SELETIVO']), delta_color="inverse")
        
        tab1, tab2 = st.tabs(["Auditoria Completa", "Itens Lei"])
        with tab1: st.dataframe(df_analise, use_container_width=True)
        with tab2: st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")], use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False, sheet_name='Resultado')
        
        st.download_button("📥 Baixar Excel (.xlsx)", buffer, "Auditoria_Fiscal.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")