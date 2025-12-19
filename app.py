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
    .stMetric {background-color: #fff; border-left: 5px solid #154360; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal 12.0 (Híbrido)")
st.caption("Leitura do Site + Texto de Segurança (Garante Batata 20.04 e Queijos)")
st.divider()

# --- 2. TEXTO DE SEGURANÇA (BACKUP MANUAL) ---
# Colei aqui os trechos criticos que você me enviou para garantir que o robô leia mesmo se o site falhar.
TEXTO_BACKUP = """
ANEXO I - CESTA BÁSICA
Arroz 1006.20 1006.30 1006.40.00
Leite 0401.10.10 0401.20.10 
Feijões 0713.33.19
Carnes 02.01 02.02 02.03 02.04 02.07
Peixes 03.02 03.03 03.04
Queijos 0406.10.10 0406.90.10
Massas 1902.1

ANEXO VII - ALIMENTOS REDUZIDOS 60%
Produtos hortícolas posições 07.01 07.02 07.03 07.04 07.05 07.06 07.07 07.08 07.09 07.10
Frutas posições 08.03 08.04 08.05 08.06 08.07 08.08 08.09 08.10 08.11
Raízes e tubérculos posição 07.14
Batata 20.04 20.05 (Produtos hortícolas cozidos)
Extrato de tomate 2002.90.00
Sucos 20.09
Pão de forma 1905.90.10

ANEXO VIII - HIGIENE PESSOAL 60%
Sabões 3401.11.90
Dentifrícios 3306.10.00
Fraldas 9619.00.00
Papel higiênico 4818.10.00
"""

# --- 3. CONFIGURAÇÃO DOS ANEXOS ---
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica (Zero)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)", "Caps": ["02","03","04","07","08","09","10","11","12","15","16","17","18","19","20","21","23","25"]},
    "ANEXO IV": {"Descricao": "Dispositivos Médicos (Red. 60%)", "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)", "Caps": ["30","37","39","40","84","90","94"]},
    "ANEXO VII": {"Descricao": "Alimentos (Red. 60%)", "cClassTrib": "200003", "CST": "20", "Status": "REDUZIDA 60% (Anexo VII)", "Caps": ["03","04","07","08","10","11","12","15","16","19","20","21","22"]},
    "ANEXO VIII": {"Descricao": "Higiene (Red. 60%)", "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo VIII)", "Caps": ["33","34","38","48","96"]},
    "ANEXO XII": {"Descricao": "Disp. Médicos (Zero)", "cClassTrib": "200005", "CST": "40", "Status": "ZERO (Anexo XII)", "Caps": ["90"]},
    "ANEXO XIV": {"Descricao": "Medicamentos (Zero)", "cClassTrib": "200009", "CST": "40", "Status": "ZERO (Anexo XIV)", "Caps": ["28","29","30"]},
    "ANEXO XV": {"Descricao": "Hortifruti/Ovos (Zero)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo XV)", "Caps": ["04","06","07","08"]}
}

def verificar_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    # Bloqueia alcool, fumo, carros, armas
    if any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93']):
        return True
    return False

# --- 4. MOTOR DE LEITURA (SITE + MANUAL) ---
@st.cache_data
def carregar_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            return df
    except: return pd.DataFrame()

def extrair_ncms_do_texto(texto, mapa_existente, origem_nome):
    """Função auxiliar que extrai NCMs de qualquer texto"""
    
    # 1. Limpeza para facilitar regex
    texto_limpo = re.sub(r'\s+', ' ', texto) 
    
    # Encontra onde começa cada anexo no texto
    anexos_pos = []
    for anexo in CONFIG_ANEXOS.keys():
        pos = texto_limpo.upper().find(anexo)
        if pos != -1: anexos_pos.append((pos, anexo))
    anexos_pos.sort()
    
    for i in range(len(anexos_pos)):
        nome_anexo = anexos_pos[i][1]
        inicio = anexos_pos[i][0]
        fim = anexos_pos[i+1][0] if i+1 < len(anexos_pos) else len(texto_limpo)
        bloco = texto_limpo[inicio:fim]
        
        # --- EXTRAÇÃO (REGEX SIMPLIFICADO) ---
        # Captura 1006.30.00
        ncms_8 = re.findall(r'(\d{4}\.\d{2}\.\d{2})', bloco)
        # Captura 1006.30
        ncms_6 = re.findall(r'(\d{4}\.\d{2})', bloco)
        # Captura 20.04 (Posição) - O SEGREDO DA BATATA
        ncms_4 = re.findall(r'(?<!\d)(\d{2}\.\d{2})(?!\d)', bloco) 
        
        caps_validos = CONFIG_ANEXOS[nome_anexo]["Caps"]
        
        # Função interna para salvar
        def salvar(codigo):
            c_limpo = codigo.replace('.', '')
            # Verifica se o capitulo é permitido para evitar erros (ex: Queijo em Higiene)
            if not caps_validos or any(c_limpo.startswith(cap) for cap in caps_validos):
                # Só sobrescreve se ainda não existir ou se for do Backup (prioridade)
                if c_limpo not in mapa_existente or origem_nome == "BACKUP":
                    mapa_existente[c_limpo] = nome_anexo

        for n in ncms_8: salvar(n)
        for n in ncms_6: salvar(n)
        for n in ncms_4: salvar(n)
        
    return mapa_existente

@st.cache_data
def mapear_total():
    mapa = {}
    
    # 1. Tenta ler do Site (Pode falhar em formatação)
    try:
        url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        texto_site = soup.get_text(separator=' ')
        mapa = extrair_ncms_do_texto(texto_site, mapa, "SITE")
    except: pass
    
    # 2. Lê do Backup Manual (Garante precisão no que você mandou)
    mapa = extrair_ncms_do_texto(TEXTO_BACKUP, mapa, "BACKUP")
    
    return mapa

# --- 5. CLASSIFICAÇÃO ---
def classificar(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm = str(ncm).replace('.', '')
    cfop = str(cfop).replace('.', '')
    
    if verificar_seletivo(ncm):
        return '000001', 'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava'

    # Hierarquia: 8 -> 6 -> 4 -> 2 digitos
    anexo = None
    origem = "Regra Geral"
    
    # Verifica todas as possibilidades
    possibilidades = [ncm, ncm[:6], ncm[:4], ncm[:2]] # Ex: 20041000, 200410, 2004, 20
    
    for tentativa in possibilidades:
        if tentativa in mapa_anexos:
            anexo = mapa_anexos[tentativa]
            origem = f"{anexo} (via {tentativa})"
            break # Achou, parou
    
    if cfop.startswith('7'): return '410004', 'Exportação', 'IMUNE', '50', 'Não'
    
    if anexo:
        regra = CONFIG_ANEXOS[anexo]
        return regra['cClassTrib'], f"{regra['Descricao']} - {origem}", regra['Status'], regra['CST'], origem
    
    else:
        # Fallback JSON
        termo = "tributação integral"
        if ncm.startswith('30'): termo = "medicamentos"
        elif ncm.startswith('10'): termo = "cesta básica"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return '000001', 'Padrão - Tributação Integral', 'PADRAO', '01', origem

# --- 6. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=50)
    st.subheader("Painel de Controle")
    with st.spinner("Carregando Regras..."):
        mapa = mapear_total()
    st.success(f"Regras Carregadas: {len(mapa)}")
    
    # Teste Rápido
    teste = st.text_input("Testar NCM (Ex: 2004, 0201):")
    if teste:
        chave = teste.replace('.', '')
        if chave in mapa: st.info(f"✅ {chave} -> {mapa[chave]}")
        else: st.error(f"❌ {chave} não encontrado.")
        
    uploaded_files = st.file_uploader("XMLs", type=['xml'], accept_multiple_files=True)

if uploaded_files:
    if df_regras.empty: st.warning("Sem JSON.")
    lista = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    prog = st.progress(0)
    
    for i, arq in enumerate(uploaded_files):
        try:
            tree = ET.parse(arq)
            root = tree.getroot()
            chave = root.find('.//ns:infNFe', ns).attrib.get('Id', '')[3:]
            for det in root.findall('.//ns:det', ns):
                prod = det.find('ns:prod', ns)
                lista.append({
                    'Chave NFe': chave,
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Valor': float(prod.find('ns:vProd', ns).text)
                })
        except: continue
        prog.progress((i+1)/len(uploaded_files))
        
    df = pd.DataFrame(lista)
    if not df.empty:
        df_res = df.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
        res = df_res.apply(lambda r: classificar(r['NCM'], r['CFOP'], r['Produto'], df_regras, mapa), axis=1, result_type='expand')
        df_res[['cClassTrib', 'Descrição', 'Status', 'CST', 'Origem']] = res
        
        st.write("### Auditoria Híbrida (Site + Backup)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens", len(df_res))
        c2.metric("Na Lei", len(df_res[df_res['Origem'].str.contains("ANEXO")]))
        c3.metric("Seletivo", len(df_res[df_res['Status'] == "ALERTA SELETIVO"]), delta_color="inverse")
        
        tab1, tab2 = st.tabs(["Geral", "Destaques Lei"])
        with tab1: st.dataframe(df_res, use_container_width=True)
        with tab2: st.dataframe(df_res[df_res['Origem'].str.contains("ANEXO")], use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_res.to_excel(writer, index=False)
        st.download_button("Baixar Excel (.xlsx)", buffer, "Auditoria_12.xlsx", "primary")