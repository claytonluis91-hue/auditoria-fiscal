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
    h1 {color: #1F618D;}
    .stMetric {background-color: #fff; padding: 15px; border-radius: 8px; border-left: 5px solid #1F618D; box-shadow: 0 2px 4px rgba(0,0,0,0.1);}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal Inteligente 10.0")
st.caption("Leitura Hierárquica: Capítulos (2) > Posições (4) > NCMs (8)")
st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS ---
# Mantemos sua configuração rica dos anexos
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica (Aliq. Zero)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)", "Capitulos_Permitidos": ["02","03","04","07","08","09","10","11","12","15","16","17","18","19","20","21","23","25"]},
    "ANEXO II": {"Descricao": "Serv. Educação (Red. 60%)", "cClassTrib": "200020", "CST": "20", "Status": "REDUZIDA 60% (Anexo II)", "Capitulos_Permitidos": []}, # Serviços não tem NCM, mas deixamos aqui
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
    # Bloqueia Álcool, Tabaco, Carros, Armas
    if any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93']):
        return True
    return False

# --- 4. LEITURA HIERÁRQUICA (O NOVO CÉREBRO) ---
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
        texto = re.sub(r'\s+', ' ', texto) # Texto limpo, mas COM pontuação
        
        # Mapeia onde começa cada anexo
        anexos_pos = []
        for anexo in CONFIG_ANEXOS.keys():
            pos = texto.upper().find(anexo)
            if pos != -1: anexos_pos.append((pos, anexo))
        anexos_pos.sort()
        
        # Loop pelos Anexos
        for i in range(len(anexos_pos)):
            nome_anexo = anexos_pos[i][1]
            inicio = anexos_pos[i][0]
            fim = anexos_pos[i+1][0] if i+1 < len(anexos_pos) else len(texto)
            
            bloco = texto[inicio:fim] # Bloco de texto com pontuação preservada
            
            # --- EXTRAÇÃO HIERÁRQUICA ---
            
            # 1. NCMs Completos (8 dígitos): 1006.30.00 ou 10063000
            ncms_full = re.findall(r'\b\d{4}\.?\d{2}\.?\d{2}\b', bloco)
            
            # 2. Posições (4 dígitos): 20.04 ou 07.01 (Aqui está o pulo do gato!)
            # Procuramos XX.XX explicitamente
            posicoes = re.findall(r'\b\d{2}\.\d{2}\b', bloco)
            
            # 3. Capítulos (2 dígitos): "Capítulo 10" ou "capítulo 12"
            capitulos = re.findall(r'Capítulo\s+(\d{1,2})', bloco, re.IGNORECASE)
            
            # --- PROCESSAMENTO ---
            capitulos_aceitos = CONFIG_ANEXOS[nome_anexo]["Capitulos_Permitidos"]
            
            # Grava 8 Dígitos
            for n in ncms_full:
                n_limpo = n.replace('.', '')
                if len(n_limpo) == 8:
                    if not capitulos_aceitos or any(n_limpo.startswith(c) for c in capitulos_aceitos):
                        mapa_ncm_anexo[n_limpo] = nome_anexo

            # Grava 4 Dígitos (Posições) - Ex: Grava "2004"
            for p in posicoes:
                p_limpo = p.replace('.', '')
                if len(p_limpo) == 4:
                    if not capitulos_aceitos or any(p_limpo.startswith(c) for c in capitulos_aceitos):
                        if p_limpo not in mapa_ncm_anexo: # Prioridade para regras mais específicas se houver
                            mapa_ncm_anexo[p_limpo] = nome_anexo
            
            # Grava 2 Dígitos (Capítulos)
            for c in capitulos:
                c_limpo = c.zfill(2) # Garante que "7" vire "07"
                if not capitulos_aceitos or c_limpo in capitulos_aceitos:
                    if c_limpo not in mapa_ncm_anexo:
                        mapa_ncm_anexo[c_limpo] = nome_anexo

        return mapa_ncm_anexo
    except Exception as e:
        return {}

# --- 5. CLASSIFICAÇÃO COM CASCATA ---

def classificar_item_master(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm_limpo = str(ncm).replace('.', '')
    cfop_limpo = str(cfop).replace('.', '')
    
    # Seletivo (Bloqueio)
    if verificar_imposto_seletivo(ncm_limpo):
        return '000001', 'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava de Segurança'

    # --- CASCATA DE HIERARQUIA (AQUI RESOLVE A BATATA) ---
    anexo_encontrado = None
    origem = "Regra Geral"
    
    # 1. Tenta match exato (8 dígitos) - Ex: 20041000
    if ncm_limpo in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo]
        origem = f"{anexo_encontrado} (NCM Exato)"
        
    # 2. Tenta match de Posição (4 dígitos) - Ex: 2004
    elif ncm_limpo[:4] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
        origem = f"{anexo_encontrado} (Pela Posição {ncm_limpo[:4]})"
        
    # 3. Tenta match de Capítulo (2 dígitos) - Ex: 07
    elif ncm_limpo[:2] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:2]]
        origem = f"{anexo_encontrado} (Pelo Capítulo {ncm_limpo[:2]})"

    # Aplica Regras
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
    uploaded_files = st.file_uploader("XMLs", type=['xml'], accept_multiple_files=True)
    with st.spinner("Lendo Lei Hierárquica..."):
        mapa_anexos = mapear_anexos_online()
    if mapa_anexos: st.success(f"🟢 Conectado: {len(mapa_anexos)} regras mapeadas.")

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
        
        st.write("### Auditoria Fiscal (Hierárquica)")
        c1,c2,c3 = st.columns(3)
        c1.metric("Itens", len(df_analise))
        c2.metric("Encontrados na Lei", len(df_analise[df_analise['Origem Legal'].str.contains("Anexo")]))
        c3.metric("Alertas Seletivo", len(df_analise[df_analise['Status'] == "ALERTA SELETIVO"]), delta_color="inverse")
        
        tab1, tab2 = st.tabs(["Geral", "Destaques Lei"])
        with tab1: st.dataframe(df_analise, use_container_width=True)
        with tab2: st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("Anexo")], use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False)
        st.download_button("Baixar Excel (.xlsx)", buffer, "Auditoria_10.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")