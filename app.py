import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import io
import os

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Auditoria Fiscal - LCP 214", page_icon="⚖️", layout="wide")
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #1B4F72;}
    .stMetric {background-color: #fff; border-left: 5px solid #1B4F72; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);}
    div[data-testid="stExpander"] div[role="button"] p {font-size: 1.1rem; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal 16.0 (Expansão Inteligente)")
st.caption("Correção: Generalização de Capítulos e Posições do Anexo VII")
st.divider()

# --- 2. LISTA MESTRA (REFINADA) ---
TEXTO_MESTRA = """
ANEXO I (ZERO)
1006.20 1006.30 1006.40.00 (Arroz)
0401.10.10 0401.10.90 0401.20.10 0401.20.90 0401.40.10 0401.50.10 (Leite)
0402.10.10 0402.10.90 0402.21.10 0402.21.20 0402.29.10 0402.29.20 (Leite Pó)
1901.10.10 1901.10.90 2106.90.90 (Fórmulas Infantis)
0405.10.00 (Manteiga) 1517.10.00 (Margarina)
0713.33.19 0713.33.29 0713.33.99 0713.35.90 (Feijões)
09.01 2101.1 (Café)
1513.21.20 (Óleo Babaçu)
1106.20.00 1903.00.00 1102.20.00 1103.13.00 1104.19.00 1104.23.00 (Farinhas Específicas Zero)
1101.00.10 1104.12.00 1104.22.00 1102.90.00 (Trigo/Aveia Zero)
1701.14.00 1701.99.00 1902.1 (Açúcar/Massas Zero)
1905.90.90 1901.20.10 1901.20.90 (Pão Francês)
02.01 02.02 02.03 02.04 02.07 0206.2 0206.4 0210.1 (Carnes)
03.02 03.03 03.04 (Peixes)
0406.10.10 0406.10.90 0406.20.00 0406.90.10 0406.90.20 0406.90.30 (Queijos)
2501.00.20 2501.00.90 09.03 (Sal/Mate)

ANEXO VII (RED 60%)
0306.1 0306.3 0307 (Crustáceos/Moluscos)
0403 (Leite Fermentado/Iogurte) 2202.99.00 (Bebida Láctea)
0409.00.00 (Mel)
1101 1102 1103 1104 1105 1106 1208 (Farinhas/Grãos/Sêmolas Gerais)
1108 (Amidos)
1507 1508 1511 1512 1513 1514 1515 (Óleos Vegetais Gerais)
1902 (Massas Gerais)
2009 (Sucos) 2008 (Polpas/Conservas) 
1905.90.10 (Pão de Forma)
2002 (Tomates Prep)
2004 2005 (Hortícolas Cozidos)
Capítulo 10 (Cereais)
Capítulo 12 (Sementes)
Capítulo 07 (Hortícolas Processados - Exceção do XV)
Capítulo 08 (Frutas Processadas - Exceção do XV)

ANEXO VIII (RED 60%)
3401 (Sabões)
3306 (Higiene Bucal)
9603.21.00 (Escovas)
4818.10.00 (Papel Higiênico)
9619.00.00 (Fraldas)

ANEXO XIV (ZERO)
3004 3002 (Medicamentos Gerais)

ANEXO XV (ZERO)
0407.2 (Ovos)
0701 0702 0703 0704 0705 0706 0708 0709 0710 (Hortifruti Fresco)
0803 0804 0805 0806 0807 0808 0809 0810 0811 (Frutas Frescas)
0714 0801 (Raízes/Coco)
"""

# --- 3. CONFIGURAÇÃO TRIBUTÁRIA ---
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica Nacional", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)", "Caps": []},
    "ANEXO IV": {"Descricao": "Dispositivos Médicos", "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)", "Caps": ["30","90"]},
    "ANEXO VII": {"Descricao": "Alimentos Reduzidos", "cClassTrib": "200003", "CST": "20", "Status": "REDUZIDA 60% (Anexo VII)", "Caps": ["03","04","07","08","10","11","12","15","16","19","20","21","22"]},
    "ANEXO VIII": {"Descricao": "Higiene Pessoal e Limpeza", "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo VIII)", "Caps": ["33","34","48","96"]},
    "ANEXO XII": {"Descricao": "Dispositivos Médicos (Zero)", "cClassTrib": "200005", "CST": "40", "Status": "ZERO (Anexo XII)", "Caps": ["90"]},
    "ANEXO XIV": {"Descricao": "Medicamentos (Zero)", "cClassTrib": "200009", "CST": "40", "Status": "ZERO (Anexo XIV)", "Caps": ["30"]},
    "ANEXO XV": {"Descricao": "Hortifruti e Ovos", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo XV)", "Caps": ["04","06","07","08"]}
}

# --- 4. CARREGAMENTO ---
@st.cache_data
def carregar_tipi(uploaded_file=None):
    arquivo = uploaded_file if uploaded_file else ("tipi.xlsx" if os.path.exists("tipi.xlsx") else None)
    if not arquivo: return pd.DataFrame()
    try:
        try: df = pd.read_excel(arquivo, dtype=str)
        except: df = pd.read_csv(arquivo, dtype=str, on_bad_lines='skip')
        for col in df.columns: df[col] = df[col].astype(str).str.strip()
        df['NCM_Limpo'] = df.iloc[:, 0].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
        df = df[df['NCM_Limpo'].str.len().isin([4, 8])]
        return df.set_index('NCM_Limpo')
    except: return pd.DataFrame()

@st.cache_data
def carregar_json_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            if 'Descrição do Código da Classificação Tributária' in df.columns:
                df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            else: df['Busca'] = ""
            return df
    except: return pd.DataFrame(columns=['Busca'])

def extrair_regras(texto_fonte, mapa_existente, nome_fonte):
    texto = re.sub(r'\s+', ' ', texto_fonte)
    anexos_pos = []
    for anexo in CONFIG_ANEXOS.keys():
        pos = texto.upper().find(anexo)
        if pos != -1: anexos_pos.append((pos, anexo))
    anexos_pos.sort()
    
    for i in range(len(anexos_pos)):
        nome_anexo = anexos_pos[i][1]
        inicio = anexos_pos[i][0]
        fim = anexos_pos[i+1][0] if i+1 < len(anexos_pos) else len(texto)
        bloco = texto[inicio:fim]
        
        ncms_raw = re.findall(r'(?<!\d)(\d{2,4}\.?\d{0,2}\.?\d{0,2})(?!\d)', bloco)
        caps = CONFIG_ANEXOS[nome_anexo]["Caps"]
        
        for codigo in ncms_raw:
            c = codigo.replace('.', '')
            if len(c) in [4,6,8]:
                if not caps or any(c.startswith(cap) for cap in caps):
                    # PRIORIDADE: Backup > Site
                    # Além disso, se já existe uma regra, só sobrescreve se a nova for "mais específica" 
                    # (isso é complexo, então vamos confiar na ordem da lista mestra e priorizar Backup)
                    if c not in mapa_existente or nome_fonte == "BACKUP":
                        mapa_existente[c] = nome_anexo
                        
                        # --- EXPANSÃO INTELIGENTE (NOVIDADE V16) ---
                        # Se achamos 1101.00.10, adicionamos também 1101 e 110100 como válidos
                        # Isso garante que a família seja reconhecida
                        if len(c) == 8:
                            pai = c[:4]
                            if pai not in mapa_existente: mapa_existente[pai] = nome_anexo
                        if len(c) == 6:
                            pai = c[:4]
                            if pai not in mapa_existente: mapa_existente[pai] = nome_anexo

    return mapa_existente

@st.cache_data
def carregar_base_legal():
    mapa = {}
    # 1. Site
    try:
        url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        mapa = extrair_regras(soup.get_text(separator=' '), mapa, "SITE")
    except: pass
    
    # 2. Backup Manual (Garantia)
    mapa = extrair_regras(TEXTO_MESTRA, mapa, "BACKUP")
    
    # 3. CAPÍTULOS INTEIROS (FORÇA BRUTA PARA ANEXO VII)
    # Se o item começar com 10, 11, 12 e não tiver regra específica (como Zero), cai no VII.
    caps_anexo_vii = ['10', '11', '12'] 
    for cap in caps_anexo_vii:
        if cap not in mapa:
            mapa[cap] = "ANEXO VII"
            
    return mapa

# --- 5. LÓGICA ---
def verificar_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    return any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93'])

def classificar_item(row, mapa_regras, df_json, df_tipi):
    ncm = str(row['NCM']).replace('.', '')
    cfop = str(row['CFOP']).replace('.', '')
    
    validacao = "⚠️ NCM não cadastrado na TIPI"
    if not df_tipi.empty:
        if ncm in df_tipi.index: validacao = "✅ NCM Válido"
        elif ncm[:4] in df_tipi.index: validacao = "✅ Posição Válida"

    if verificar_seletivo(ncm):
        return '000001', f'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava', validacao

    anexo, origem = None, "Regra Geral"
    
    # Busca Hierárquica: 8 -> 6 -> 4 -> 2 dígitos (Capítulo)
    for tent in [ncm, ncm[:6], ncm[:4], ncm[:2]]:
        if tent in mapa_regras:
            anexo = mapa_regras[tent]
            origem = f"{anexo} (Via {tent})"
            break
            
    if cfop.startswith('7'): 
        return '410004', 'Exportação', 'IMUNE', '50', 'CFOP', validacao
        
    elif anexo:
        regra = CONFIG_ANEXOS[anexo]
        return regra['cClassTrib'], f"{regra['Descricao']} - {origem}", regra['Status'], regra['CST'], origem, validacao
    
    else:
        termo = "medicamentos" if ncm.startswith('30') else ("cesta básica" if ncm.startswith('10') else "tributação integral")
        if not df_json.empty and 'Busca' in df_json.columns:
            res = df_json[df_json['Busca'].str.contains(termo, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem, validacao

    return '000001', 'Padrão - Tributação Integral', 'PADRAO', '01', origem, validacao

# --- 6. INTERFACE ---
df_regras_json = carregar_json_regras()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=60)
    st.markdown("### Painel de Controle")
    uploaded_xmls = st.file_uploader("1. XMLs de Venda", type=['xml'], accept_multiple_files=True)
    uploaded_tipi = st.file_uploader("2. Atualizar TIPI (Opcional)", type=['xlsx', 'csv'])
    st.divider()
    with st.spinner("Carregando..."):
        mapa_lei = carregar_base_legal()
        df_tipi = carregar_tipi(uploaded_tipi) 
    st.success(f"⚖️ Lei Mapeada: {len(mapa_lei)} regras")
    if not df_tipi.empty: st.success(f"📚 TIPI Carregada: {len(df_tipi)} códigos")

if uploaded_xmls:
    lista_itens = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    prog = st.progress(0)
    
    for i, arquivo in enumerate(uploaded_xmls):
        try:
            tree = ET.parse(arquivo)
            root = tree.getroot()
            infNFe = root.find('.//ns:infNFe', ns)
            chave = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else 'N/A'
            for det in root.findall('.//ns:det', ns):
                prod = det.find('ns:prod', ns)
                c_prod = prod.find('ns:cProd', ns).text
                lista_itens.append({
                    'Cód. Produto': c_prod,
                    'Chave NFe': chave,
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Valor': float(prod.find('ns:vProd', ns).text)
                })
        except: continue
        prog.progress((i+1)/len(uploaded_xmls))
    
    if lista_itens:
        df_base = pd.DataFrame(lista_itens)
        df_analise = df_base.drop_duplicates(subset=['Cód. Produto', 'NCM', 'CFOP']).copy()
        
        resultados = df_analise.apply(
            lambda row: classificar_item(row, mapa_lei, df_regras_json, df_tipi), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI']] = resultados
        
        cols_principal = ['Cód. Produto', 'NCM', 'Produto', 'CFOP', 'Valor', 'Novo CST', 'cClassTrib', 'Descrição', 'Status', 'Origem Legal', 'Validação TIPI']
        df_principal = df_analise[cols_principal]
        df_arquivos = df_base[['Chave NFe']].drop_duplicates().reset_index(drop=True)
        df_arquivos.columns = ['Arquivos / Chaves NFe Processadas']
        
        st.write("### 📊 Auditoria Fiscal 16.0")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Itens", len(df_principal))
        c2.metric("Na Lei", len(df_principal[df_principal['Origem Legal'].str.contains("Anexo")]))
        n_erros = len(df_principal[df_principal['Validação TIPI'].str.contains("não cadastrado")])
        c3.metric("Erros NCM", n_erros, delta="Atenção" if n_erros > 0 else None, delta_color="inverse")
        n_is = len(df_principal[df_principal['Status'] == "ALERTA SELETIVO"])
        c4.metric("Seletivo", n_is, delta="Bloqueado" if n_is > 0 else None, delta_color="inverse")
        
        tab1, tab2, tab3 = st.tabs(["Auditoria", "Arquivos", "Destaques Lei"])
        with tab1: st.dataframe(df_principal, use_container_width=True)
        with tab2: st.dataframe(df_arquivos, use_container_width=True)
        with tab3: st.dataframe(df_principal[df_principal['Origem Legal'].str.contains("Anexo")], use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_principal.to_excel(writer, index=False, sheet_name="Auditoria")
            df_arquivos.to_excel(writer, index=False, sheet_name="Arquivos Processados")
            if not df_tipi.empty:
                df_principal[df_principal['Validação TIPI'].str.contains("não cadastrado")].to_excel(writer, index=False, sheet_name="Erros NCM")
        
        st.download_button("📥 Baixar Relatório Final (.xlsx)", buffer, "Auditoria_Nascel_v16.xlsx", "primary")