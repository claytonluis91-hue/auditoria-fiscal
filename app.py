import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - Reforma Tributária",
    page_icon="⚖️",
    layout="wide"
)

# Título e Cabeçalho
st.title("⚖️ Auditoria & Classificação - Reforma Tributária")
st.markdown("""
**Instruções:** Arraste seus arquivos XML de venda para identificar a tributação correta 
(cClassTrib e CST) com base no NCM, CFOP e nas regras da Reforma Tributária.
""")
st.divider()

# --- 2. CARREGAR REGRAS (JSON) ---
@st.cache_data
def carregar_regras():
    try:
        # Busca o arquivo JSON na mesma pasta
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            # Cria coluna de busca em minúsculo para facilitar a comparação
            df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            return df
    except FileNotFoundError:
        return pd.DataFrame()

# --- 3. LÓGICA DE INTELIGÊNCIA TRIBUTÁRIA ---
def classificar_item(ncm, cfop, df_regras):
    ncm = str(ncm)
    cfop = str(cfop).replace('.', '') # Remove pontos (5.102 vira 5102)
    
    termo_busca = ""
    status = "PADRAO" 

    # --- REGRAS DE NEGÓCIO (Analista Fiscal) ---
    # Define qual termo vamos buscar no JSON baseado no NCM/CFOP
    
    # 1º: Operações Especiais (Pelo CFOP)
    if cfop.startswith('7'): 
        termo_busca = "exportação"
        status = "IMUNE"
    elif cfop in ['6109', '6110', '5109', '5110']:
        termo_busca = "zona franca"
        status = "BENEFICIO"
    elif cfop in ['5901', '5902', '5949', '6901']:
        # Se for remessa, não tem CST de tributação regular
        return '-', 'Remessa/Devolução (Não Incidência)', 'OUTROS', '999'
        
    # 2º: Tipo de Produto (Pelo NCM)
    elif ncm.startswith('30'):
        termo_busca = "medicamentos"
        status = "REDUZIDA"
    elif ncm.startswith('1006') or ncm.startswith('02') or ncm.startswith('1101'): # Arroz, Carne, Trigo
        termo_busca = "cesta básica"
        status = "ZERO"
    elif ncm.startswith('3304') or ncm.startswith('3401'):
        termo_busca = "higiene"
        status = "REDUZIDA"
    elif ncm.startswith('2710'):
        termo_busca = "combustíveis"
        status = "MONOFASICA"
    else:
        # Se não cair em nenhuma regra acima, busca a regra PADRÃO no JSON
        termo_busca = "tributação integral"
        status = "PADRAO"

    # --- BUSCA NO JSON ---
    if not df_regras.empty:
        # Tenta achar a palavra chave dentro do JSON
        resultado = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
        
        if not resultado.empty:
            # Pega os dados principais
            codigo = resultado.iloc[0]['Código da Classificação Tributária']
            desc = resultado.iloc[0]['Descrição do Código da Classificação Tributária']
            
            # --- NOVIDADE: PEGA O CST DO JSON ---
            # O .get previne erro se a coluna não existir
            cst = resultado.iloc[0].get('Código da Situação Tributária', '?')
            
            return codigo, desc, status, cst
    
    # Se definiu um termo de busca mas não achou no JSON
    return 'VERIFICAR', f'Regra definida mas não encontrada: {termo_busca}', 'ATENCAO', '?'

# --- 4. PROCESSAMENTO DOS XMLS ---
def processar_xmls(uploaded_files):
    lista_produtos = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    
    for arquivo in uploaded_files:
        try:
            tree = ET.parse(arquivo)
            root = tree.getroot()
            
            # Tenta ler dados da nota
            infNFe = root.find('.//ns:infNFe', ns)
            id_nota = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else 'N/A'
            
            det_itens = root.findall('.//ns:det', ns)
            
            for item in det_itens:
                prod = item.find('ns:prod', ns)
                
                # Tratamento de erro caso algum campo falte
                try:
                    vProd = float(prod.find('ns:vProd', ns).text)
                except:
                    vProd = 0.0

                lista_produtos.append({
                    'Chave NFe': id_nota,
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Unid': prod.find('ns:uCom', ns).text,
                    'Valor': vProd
                })
        except Exception as e:
            continue
            
    return pd.DataFrame(lista_produtos)

# --- 5. INTERFACE VISUAL ---

# Sidebar para Upload
with st.sidebar:
    st.header("📂 Importação")
    uploaded_files = st.file_uploader("Selecione arquivos XML", type=['xml'], accept_multiple_files=True)
    st.info("O processamento ocorre localmente ou na nuvem segura do Streamlit.")

# Carrega a inteligência
df_regras = carregar_regras()

if uploaded_files:
    if df_regras.empty:
        st.error("🚨 ERRO: Não encontrei o arquivo 'classificacao_tributaria.json'. Verifique se ele está na pasta.")
    else:
        with st.spinner('Lendo XMLs e Cruzando com o JSON...'):
            df_base = processar_xmls(uploaded_files)
            
            if not df_base.empty:
                # Criamos um dataframe resumido para análise (agrupado por produto único)
                df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
                
                # APLICA A CLASSIFICAÇÃO (RETORNA 4 VALORES AGORA)
                resultados = df_analise.apply(
                    lambda row: classificar_item(row['NCM'], row['CFOP'], df_regras), axis=1, result_type='expand'
                )
                
                # Cria as colunas novas
                df_analise['Novo cClassTrib'] = resultados[0]
                df_analise['Descrição Legal'] = resultados[1]
                df_analise['Status'] = resultados[2]
                df_analise['Novo CST'] = resultados[3] # <--- AQUI ESTÁ O SEU CST DO JSON
                
                # --- DASHBOARD DE RESUMO ---
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Notas Lidas", len(uploaded_files))
                col2.metric("Produtos Únicos", len(df_analise))
                col3.metric("Valor Total Processado", f"R$ {df_base['Valor'].sum():,.2f}")
                
                atencao = len(df_analise[df_analise['Status'] == 'ATENCAO'])
                col4.metric("Itens p/ Revisar", atencao, delta_color="inverse" if atencao > 0 else "normal")
                
                st.divider()
                
                # --- VISUALIZAÇÃO DOS DADOS ---
                tab1, tab2 = st.tabs(["📋 Tabela Detalhada", "📊 Gráfico de Status"])
                
                with tab1:
                    filtro = st.multiselect("Filtrar por Status:", df_analise['Status'].unique(), default=df_analise['Status'].unique())
                    
                    # Reorganizando as colunas para o CST aparecer junto com o cClassTrib
                    colunas_ordem = ['NCM', 'Produto', 'CFOP', 'Novo cClassTrib', 'Novo CST', 'Descrição Legal', 'Status', 'Valor']
                    # Garante que só pegamos colunas que existem (caso o XML não tenha alguma)
                    cols_finais = [c for c in colunas_ordem if c in df_analise.columns]
                    
                    st.dataframe(df_analise[df_analise['Status'].isin(filtro)][cols_finais], use_container_width=True)
                
                with tab2:
                    st.bar_chart(df_analise['Status'].value_counts())
                
                # --- DOWNLOAD ---
                csv = df_analise.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
                st.download_button(
                    label="📥 Baixar Relatório em Excel (CSV)",
                    data=csv,
                    file_name="Analise_Tributaria_Completa.csv",
                    mime="text/csv"
                )
                
            else:
                st.warning("Nenhum dado de produto encontrado nos XMLs.")

else:
    st.info("Aguardando arquivos XML...")