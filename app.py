import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import io

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Auditoria Fiscal 13.0 (TIPI Integrada)", page_icon="⚖️", layout="wide")
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #1B4F72;}
    .stMetric {background-color: #fff; border-left: 5px solid #1B4F72; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);}
    div[data-testid="stExpander"] div[role="button"] p {font-size: 1.1rem; font-weight: bold;}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal 13.0")
st.caption("Cruzamento: XML vs LCP 214 (Lista Mestra) vs Tabela TIPI (Validação)")
st.divider()

# --- 2. LISTA MESTRA (BASEADA NO SEU RESUMO) ---
# Esta lista garante que o sistema conheça as regras mesmo se o site falhar.
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
1106.20.00 1903.00.00 1102.20.00 1103.13.00 1104.19.00 1104.23.00 (Farinhas/Grãos)
1101.00.10 1104.12.00 1104.22.00 1102.90.00 (Trigo/Aveia)
1701.14.00 1701.99.00 1902.1 (Açúcar/Massas)
1905.90.90 1901.20.10 1901.20.90 (Pão Francês)
02.01 02.02 02.03 02.04 02.07 0206.2 0206.4 0210.1 (Carnes)
03.02 03.03 03.04 (Peixes)
0406.10.10 0406.10.90 0406.20.00 0406.90.10 0406.90.20 0406.90.30 (Queijos)
2501.00.20 2501.00.90 09.03 (Sal/Mate)

ANEXO IV (RED 60%)
3926.90.30 3701.10.10 9021.50.00 9021.90.12 4015.1 9018.31 9018.32

ANEXO VII (RED 60%)
0306.11 0409.00.00 (Mel)
1101 11.02 11.05 11.06 12.08 (Farinhas)
15.08 15.11 15.12 15.13 15.14 15.15 (Óleos)
20.09 20.08 (Sucos/Polpas)
1905.90.10 (Pão de Forma)
20.04 20.05 (Hortícolas Processados/Batata)

ANEXO VIII (RED 60%)
3401.11.90 3401.19.00 (Sabões)
3306.10.00 (Dentifrícios)
9603.21.00 (Escovas)
4818.10.00 (Papel Higiênico)
9619.00.00 (Fraldas/Absorventes)

ANEXO XIV (ZERO)
3004.90.69 3004.90.79 3002.15.90 3002.41.29 (Lista Medicamentos)

ANEXO XV (ZERO)
0407.2 (Ovos)
07.01 07.02 07.03 07.04 07.05 07.06 07.08 07.09 07.10 (Hortifruti)
08.03 08.04 08.05 08.06 08.07 08.08 08.09 08.10 08.11 (Frutas)
07.14 0801.1 (Raízes/Coco)
"""

# --- 3. CONFIGURAÇÃO TRIBUTÁRIA ---
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica Nacional", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)", "Caps": []},
    "ANEXO IV": {"Descricao": "Dispositivos Médicos", "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)", "Caps": ["30","90"]},
    "ANEXO VII": {"Descricao": "Alimentos Reduzidos", "cClassTrib": "200003", "CST": "20", "Status": "REDUZIDA 60% (Anexo VII)", "Caps": ["03","04","11","15","16","19","20"]},
    "ANEXO VIII": {"Descricao": "Higiene Pessoal e Limpeza", "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo VIII)", "Caps": ["33","34","48","96"]},
    "ANEXO XII": {"Descricao": "Dispositivos Médicos (Zero)", "cClassTrib": "200005", "CST": "40", "Status": "ZERO (Anexo XII)", "Caps": ["90"]},
    "ANEXO XIV": {"Descricao": "Medicamentos (Zero)", "cClassTrib": "200009", "CST": "40", "Status": "ZERO (Anexo XIV)", "Caps": ["30"]},
    "ANEXO XV": {"Descricao": "Hortifruti e Ovos", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo XV)", "Caps": ["04","07","08"]}
}

# --- 4. FUNÇÕES DE CARREGAMENTO ---

@st.cache_data
def carregar_tipi(uploaded_file):
    """Lê a tabela TIPI para validar NCMs"""
    if uploaded_file is None: return pd.DataFrame()
    try:
        # Tenta ler como CSV primeiro (comum em conversões)
        try:
            df = pd.read_csv(uploaded_file, dtype=str, on_bad_lines='skip')
        except:
            # Se falhar, tenta Excel
            df = pd.read_excel(uploaded_file, dtype=str)
            
        # Limpa colunas para achar NCM e Descrição
        # Assume que a primeira coluna com números é NCM
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
        # Cria coluna 'NCM_Limpo'
        # Pega a primeira coluna (geralmente A) como NCM
        df['NCM_Limpo'] = df.iloc[:, 0].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
        df = df[df['NCM_Limpo'].str.len().isin([4, 8])] # Filtra só o que parece NCM ou Posição
        return df.set_index('NCM_Limpo')
    except Exception as e:
        st.warning(f"Não foi possível processar a TIPI: {e}")
        return pd.DataFrame()

@st.cache_data
def carregar_json_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            return pd.DataFrame(dados)
    except: return pd.DataFrame()

def extrair_regras(texto_fonte, mapa_existente, nome_fonte):
    """Extrai NCMs (8), Subposições (6) e Posições (4) do texto"""
    texto = re.sub(r'\s+', ' ', texto_fonte) # Limpa espaços
    
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
        
        # Regex para pegar formatos: 1006.30.00, 1006.30, 20.04 e também 10063000
        # O padrão (?<!\d) garante que não pegue meio de número
        ncms_raw = re.findall(r'(?<!\d)(\d{2,4}\.?\d{0,2}\.?\d{0,2})(?!\d)', bloco)
        
        caps_permitidos = CONFIG_ANEXOS[nome_anexo]["Caps"]
        
        for codigo in ncms_raw:
            c_limpo = codigo.replace('.', '')
            if len(c_limpo) in [4, 6, 8]: # Apenas Posição, Sub ou Item
                # Filtro de Coerência (Evita erro grosseiro como Queijo no Anexo VIII)
                if not caps_permitidos or any(c_limpo.startswith(cap) for cap in caps_permitidos):
                    # Prioridade: Backup > Site
                    if c_limpo not in mapa_existente or nome_fonte == "BACKUP":
                        mapa_existente[c_limpo] = nome_anexo
    return mapa_existente

@st.cache_data
def carregar_base_legal():
    mapa = {}
    
    # 1. Leitura do Site Oficial (Automático)
    try:
        url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        texto_site = soup.get_text(separator=' ')
        mapa = extrair_regras(texto_site, mapa, "SITE")
    except: pass
    
    # 2. Leitura da Lista Mestra (Manual/Backup - Prioridade Máxima)
    mapa = extrair_regras(TEXTO_MESTRA, mapa, "BACKUP")
    
    return mapa

# --- 5. LÓGICA PRINCIPAL ---

def verificar_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    # Bloqueia (Álcool, Fumo, Veículos, Armas) de terem benefício
    if any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93']):
        return True
    return False

def classificar_item(row, mapa_regras, df_json, df_tipi):
    ncm = str(row['NCM']).replace('.', '')
    cfop = str(row['CFOP']).replace('.', '')
    
    # 1. Validação TIPI (Se disponível)
    desc_tipi = "Não validado na TIPI"
    if not df_tipi.empty:
        if ncm in df_tipi.index:
            # Pega a descrição oficial (pode estar na coluna 1 ou 2 dependendo do arquivo)
            desc_tipi = "NCM Válido (TIPI)"
        elif ncm[:4] in df_tipi.index:
            desc_tipi = "Posição Válida (TIPI)"
        else:
            desc_tipi = "⚠️ NCM não encontrado na TIPI"

    # 2. Trava de Segurança (Imposto Seletivo)
    if verificar_seletivo(ncm):
        return '000001', f'Produto sujeito a Imposto Seletivo ({desc_tipi})', 'ALERTA SELETIVO', '02', 'Trava Segurança'

    # 3. Busca Hierárquica na Lei (8 > 6 > 4 dígitos)
    anexo = None
    origem = "Regra Geral"
    
    possibilidades = [ncm, ncm[:6], ncm[:4]] # Ex: 20041000, 200410, 2004
    
    for tentativa in possibilidades:
        if tentativa in mapa_regras:
            anexo = mapa_regras[tentativa]
            origem = f"{anexo} (Via {tentativa})"
            break
            
    # 4. Define Saída
    if cfop.startswith('7'): 
        return '410004', 'Exportação', 'IMUNE', '50', 'CFOP'
        
    elif anexo:
        regra = CONFIG_ANEXOS[anexo]
        return regra['cClassTrib'], f"{regra['Descricao']} - {origem}", regra['Status'], regra['CST'], origem
    
    else:
        # Fallback JSON (Se não achou na Lei)
        termo = "tributação integral"
        if ncm.startswith('30'): termo = "medicamentos"
        elif ncm.startswith('10'): termo = "cesta básica"
        
        if not df_json.empty:
            res = df_json[df_json['Busca'].str.contains(termo, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return '000001', 'Padrão - Tributação Integral', 'PADRAO', '01', origem

# --- 6. INTERFACE ---
df_regras_json = carregar_json_regras()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=60)
    st.markdown("### Painel de Controle")
    
    # Uploads
    uploaded_xmls = st.file_uploader("1. XMLs de Venda", type=['xml'], accept_multiple_files=True)
    uploaded_tipi = st.file_uploader("2. Tabela TIPI (.xlsx ou .csv)", type=['xlsx', 'csv'])
    
    st.divider()
    
    # Status
    with st.spinner("Carregando Regras Legais..."):
        mapa_lei = carregar_base_legal()
    st.success(f"⚖️ Lei Mapeada: {len(mapa_lei)} regras")
    
    df_tipi = carregar_tipi(uploaded_tipi)
    if not df_tipi.empty:
        st.success(f"📚 TIPI Carregada: {len(df_tipi)} códigos")
    else:
        st.info("ℹ️ TIPI não carregada (Opcional)")

# Processamento Principal
if uploaded_xmls:
    lista_itens = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    progresso = st.progress(0)
    
    for i, arquivo in enumerate(uploaded_xmls):
        try:
            tree = ET.parse(arquivo)
            root = tree.getroot()
            chave = root.find('.//ns:infNFe', ns).attrib.get('Id', '')[3:]
            for det in root.findall('.//ns:det', ns):
                prod = det.find('ns:prod', ns)
                lista_itens.append({
                    'Chave NFe': chave,
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Valor': float(prod.find('ns:vProd', ns).text)
                })
        except: continue
        progresso.progress((i+1)/len(uploaded_xmls))
    
    if lista_itens:
        df_base = pd.DataFrame(lista_itens)
        df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
        
        # Executa Classificação
        resultados = df_analise.apply(
            lambda row: classificar_item(row, mapa_lei, df_regras_json, df_tipi), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'CST', 'Origem Legal']] = resultados
        
        # Validação TIPI Visual (Se disponível)
        if not df_tipi.empty:
            df_analise['Validação TIPI'] = df_analise['NCM'].apply(lambda x: "✅ OK" if x in df_tipi.index else "⚠️ Inexistente")
        
        # Dashboard
        st.write("### 📊 Auditoria Fiscal 13.0")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Itens Únicos", len(df_analise))
        c2.metric("Base Legal", len(df_analise[df_analise['Origem Legal'].str.contains("Anexo")]))
        c3.metric("Cesta/Zero", len(df_analise[df_analise['Status'].str.contains("ZERO")]))
        
        n_alertas = len(df_analise[df_analise['Status'] == "ALERTA SELETIVO"])
        c4.metric("Alertas Seletivo", n_alertas, delta="Atenção" if n_alertas > 0 else None, delta_color="inverse")
        
        # Tabelas
        tab1, tab2, tab3 = st.tabs(["Geral", "Destaques Lei", "Alertas & TIPI"])
        with tab1: st.dataframe(df_analise, use_container_width=True)
        with tab2: st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("Anexo")], use_container_width=True)
        with tab3: 
            if not df_tipi.empty:
                st.dataframe(df_analise[df_analise['Validação TIPI'] == "⚠️ Inexistente"], use_container_width=True)
            else:
                st.info("Carregue a TIPI para ver validações de NCM inexistente.")

        # Download
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False, sheet_name="Auditoria")
            if not df_tipi.empty:
                df_analise[df_analise['Validação TIPI'] == "⚠️ Inexistente"].to_excel(writer, index=False, sheet_name="Erros Cadastro")
        
        st.download_button("📥 Baixar Relatório Final (.xlsx)", buffer, "Auditoria_Nascel_v13.xlsx", "primary")