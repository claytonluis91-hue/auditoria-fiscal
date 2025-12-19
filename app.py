import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import io

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Auditoria Fiscal - LCP 214", page_icon="⚖️", layout="wide")
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #154360;}
    .stMetric {background-color: #fff; border: 1px solid #ddd; border-left: 5px solid #154360; border-radius: 5px;}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal Inteligente (Versão 11.0)")
st.caption("Correção de Leitura Hierárquica (XX.XX e XX.XX.XX)")
st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS ---
# Ajustado para permitir os capítulos corretos
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica (Aliq. Zero)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)", "Capitulos_Permitidos": ["02","03","04","07","08","09","10","11","12","15","16","17","18","19","20","21","23","25"]},
    "ANEXO IV": {"Descricao": "Dispositivos Médicos (Red. 60%)", "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)", "Capitulos_Permitidos": ["30","37","39","40","84","90","94"]},
    "ANEXO VII": {"Descricao": "Alimentos Reduzidos (Red. 60%)", "cClassTrib": "200003", "CST": "20", "Status": "REDUZIDA 60% (Anexo VII)", "Capitulos_Permitidos": ["03","04","07","08","10","11","12","15","16","19","20","21","22"]},
    "ANEXO VIII": {"Descricao": "Higiene Pessoal (Red. 60%)", "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo VIII)", "Capitulos_Permitidos": ["33","34","38","48","96"]},
    "ANEXO XII": {"Descricao": "Dispositivos Médicos (Aliq. Zero)", "cClassTrib": "200005", "CST": "40", "Status": "ZERO (Anexo XII)", "Capitulos_Permitidos": ["90"]},
    "ANEXO XIV": {"Descricao": "Medicamentos (Aliq. Zero)", "cClassTrib": "200009", "CST": "40", "Status": "ZERO (Anexo XIV)", "Capitulos_Permitidos": ["28","29","30"]},
    "ANEXO XV": {"Descricao": "Hortifruti/Ovos (Red. 100%)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo XV)", "Capitulos_Permitidos": ["04","06","07","08"]}
}

# --- 3. TRAVA DE SEGURANÇA (IS) ---
def verificar_imposto_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    # Bloqueia Álcool, Tabaco, Veículos, Armas
    if any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93']):
        return True
    return False

# --- 4. LEITURA COM REGEX TURBINADO ---
@st.cache_data
def carregar_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            return df
    except: return pd.DataFrame()

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
        
        # Encontra Anexos
        anexos_pos = []
        for anexo in CONFIG_ANEXOS.keys():
            pos = texto.upper().find(anexo)
            if pos != -1: anexos_pos.append((pos, anexo))
        anexos_pos.sort()
        
        # Loop de Extração
        for i in range(len(anexos_pos)):
            nome_anexo = anexos_pos[i][1]
            inicio = anexos_pos[i][0]
            fim = anexos_pos[i+1][0] if i+1 < len(anexos_pos) else len(texto)
            bloco = texto[inicio:fim]
            
            # --- FERRAMENTAS DE EXTRAÇÃO ---
            
            # 1. NCM Completo (8 dígitos): 1006.30.00
            ncms_8 = re.findall(r'(?<!\d)(\d{4})\.(\d{2})\.(\d{2})(?!\d)', bloco)
            
            # 2. Subposição (6 dígitos): 1006.30
            ncms_6 = re.findall(r'(?<!\d)(\d{4})\.(\d{2})(?!\d)', bloco)
            
            # 3. Posição (4 dígitos): 20.04 (AQUI RESOLVE A BATATA)
            ncms_4 = re.findall(r'(?<!\d)(\d{2})\.(\d{2})(?!\d)', bloco)
            
            # 4. Capítulos (2 dígitos): "Capítulo 10"
            caps = re.findall(r'Capítulo\s+(\d{1,2})', bloco, re.IGNORECASE)
            
            capitulos_aceitos = CONFIG_ANEXOS[nome_anexo]["Capitulos_Permitidos"]
            
            # Processa 8 dígitos
            for n in ncms_8:
                codigo = f"{n[0]}{n[1]}{n[2]}" # Junta as partes
                if not capitulos_aceitos or any(codigo.startswith(c) for c in capitulos_aceitos):
                    mapa_ncm_anexo[codigo] = nome_anexo

            # Processa 6 dígitos
            for n in ncms_6:
                codigo = f"{n[0]}{n[1]}"
                if not capitulos_aceitos or any(codigo.startswith(c) for c in capitulos_aceitos):
                    # Prioridade: Só grava se não tiver regra mais específica
                    if codigo not in mapa_ncm_anexo: mapa_ncm_anexo[codigo] = nome_anexo

            # Processa 4 dígitos (Posições)
            for n in ncms_4:
                codigo = f"{n[0]}{n[1]}"
                if not capitulos_aceitos or any(codigo.startswith(c) for c in capitulos_aceitos):
                    if codigo not in mapa_ncm_anexo: mapa_ncm_anexo[codigo] = nome_anexo

            # Processa 2 dígitos
            for c in caps:
                codigo = c.zfill(2)
                if not capitulos_aceitos or codigo in capitulos_aceitos:
                    if codigo not in mapa_ncm_anexo: mapa_ncm_anexo[codigo] = nome_anexo

        return mapa_ncm_anexo
    except Exception as e:
        st.error(f"Erro leitura: {e}")
        return {}

# --- 5. CLASSIFICAÇÃO COM CASCATA ---
def classificar_item_master(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm_limpo = str(ncm).replace('.', '')
    cfop_limpo = str(cfop).replace('.', '')
    
    if verificar_imposto_seletivo(ncm_limpo):
        return '000001', 'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava de Segurança'

    anexo_encontrado = None
    origem = "Regra Geral"
    
    # --- CASCATA DE VERIFICAÇÃO ---
    # 1. Match Exato (8 dígitos)
    if ncm_limpo in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo]
        origem = f"{anexo_encontrado} (NCM Exato)"
    # 2. Match 6 dígitos
    elif ncm_limpo[:6] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:6]]
        origem = f"{anexo_encontrado} (Subposição {ncm_limpo[:6]})"
    # 3. Match 4 dígitos (A Batata entra aqui!)
    elif ncm_limpo[:4] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
        origem = f"{anexo_encontrado} (Posição {ncm_limpo[:4]})"
    # 4. Match 2 dígitos (Capítulo)
    elif ncm_limpo[:2] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:2]]
        origem = f"{anexo_encontrado} (Capítulo {ncm_limpo[:2]})"

    if cfop_limpo.startswith('7'):
        return '410004', 'Exportação', 'IMUNE', '50', 'Não'
        
    elif anexo_encontrado:
        regra = CONFIG_ANEXOS[anexo_encontrado]
        return regra['cClassTrib'], f"{regra['Descricao']} - {origem}", regra['Status'], regra['CST'], origem
    
    else:
        # Fallback JSON
        termo_busca = "tributação integral"
        if ncm_limpo.startswith('30'): termo_busca = "medicamentos"
        elif ncm_limpo.startswith('10'): termo_busca = "cesta básica"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return '000001', 'Padrão - Tributação Integral', 'PADRAO', '01', origem

# --- 6. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=50)
    st.title("Auditor LCP 214")
    
    # --- DEBUGGER VISUAL ---
    st.markdown("### 🔍 Raio-X da Memória")
    with st.spinner("Lendo Planalto..."):
        mapa_anexos = mapear_anexos_online()
    
    if mapa_anexos:
        st.success(f"Conectado: {len(mapa_anexos)} regras.")
        teste_ncm = st.text_input("Testar NCM (ex: 2004, 1006):")
        if teste_ncm:
            # Remove pontos para buscar na chave do dicionário
            chave = teste_ncm.replace('.', '')
            if chave in mapa_anexos:
                st.info(f"✅ Encontrado: {mapa_anexos[chave]}")
            else:
                st.error("❌ Não consta na lista da Lei.")
                st.caption("Dica: Tente buscar apenas os 4 primeiros dígitos.")
    
    uploaded_files = st.file_uploader("XMLs", type=['xml'], accept_multiple_files=True)

if uploaded_files:
    if df_regras.empty: st.warning("Sem JSON de regras.")
    lista_produtos = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
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
        resultados = df_analise.apply(lambda row: classificar_item_master(row['NCM'], row['CFOP'], row['Produto'], df_regras, mapa_anexos), axis=1, result_type='expand')
        df_analise[['cClassTrib', 'Descrição', 'Status', 'CST', 'Origem Legal']] = resultados
        
        st.write("### Resultado da Auditoria")
        c1,c2,c3 = st.columns(3)
        c1.metric("Itens Analisados", len(df_analise))
        c2.metric("Encontrados na Lei", len(df_analise[df_analise['Origem Legal'].str.contains("Anexo")]))
        c3.metric("Alertas Seletivo", len(df_analise[df_analise['Status'] == "ALERTA SELETIVO"]), delta_color="inverse")
        
        tab1, tab2 = st.tabs(["Geral", "Destaques Lei"])
        with tab1: st.dataframe(df_analise, use_container_width=True)
        with tab2: st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("Anexo")], use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False)
        st.download_button("Baixar Excel (.xlsx)", buffer, "Auditoria_11.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")