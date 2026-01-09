import pandas as pd
import json
import xml.etree.ElementTree as ET
import io

# --- 1. CARREGAMENTO DE DADOS (Mantendo sua lógica original) ---
def carregar_base_legal():
    # Esta função deve retornar o seu DataFrame de regras (JSON ou Excel)
    # Se você usa um arquivo 'regras.json' ou 'base_legal.xlsx', certifique-se
    # de que o app.py está passando esse arquivo corretamente.
    try:
        # Tenta carregar localmente se existir, senão retorna vazio (será preenchido pelo app.py)
        return pd.read_json("regras.json") 
    except:
        return pd.DataFrame() # Retorna vazio se não achar, para não quebrar

def carregar_json_regras():
    # Tabela auxiliar de CSTs e definições da Reforma
    return pd.DataFrame([
        {"cClass": "000001", "Descricao": "Tributação Padrão", "Aliquota": "Cheia"},
        {"cClass": "410999", "Descricao": "Operação Não Onerosa / Isenta", "Aliquota": "Zero"},
        # Adicione outros se necessário
    ])

def carregar_tipi(uploaded_file):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                return pd.read_csv(uploaded_file, encoding='latin1', sep=';', dtype=str)
            else:
                return pd.read_excel(uploaded_file, dtype=str)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

# --- 2. PARSERS (XML e SPED) - Mantidos idênticos ---
def extrair_nome_empresa_xml(tree, ns):
    try:
        emit = tree.find('.//ns:emit', ns)
        return emit.find('ns:xNome', ns).text
    except:
        return "Empresa Desconhecida"

def processar_xml_detalhado(tree, ns, tipo_arquivo):
    itens = []
    try:
        infNFe = tree.find('.//ns:infNFe', ns)
        chave = infNFe.attrib.get('Id', '')[3:]
        ide = infNFe.find('ns:ide', ns)
        natOp = ide.find('ns:natOp', ns).text
    except:
        return []

    for det in infNFe.findall('ns:det', ns):
        prod = det.find('ns:prod', ns)
        imposto = det.find('ns:imposto', ns)
        
        item = {
            'Tipo Arquivo': tipo_arquivo,
            'Chave NFe': chave,
            'Natureza Op.': natOp,
            'Cód. Produto': prod.find('ns:cProd', ns).text,
            'Produto': prod.find('ns:xProd', ns).text,
            'NCM': prod.find('ns:NCM', ns).text,
            'CFOP': prod.find('ns:CFOP', ns).text,
            'Valor': float(prod.find('ns:vProd', ns).text),
        }
        
        # Extração Segura de Tributos
        for tributo in ['ICMS', 'PIS', 'COFINS']:
            try:
                node = imposto.find(f'.//ns:{tributo}', ns)
                if node and len(node) > 0:
                    child = node[0] # Pega CST (ex: ICMS00)
                    tag_val = f'v{tributo}'
                    val = child.find(f'ns:{tag_val}', ns)
                    item[tag_val] = float(val.text) if val is not None else 0.0
                else:
                    item[f'v{tributo}'] = 0.0
            except:
                item[f'v{tributo}'] = 0.0
        
        itens.append(item)
    return itens

def processar_sped_fiscal(file_obj):
    content = file_obj.getvalue().decode('latin1').splitlines()
    nome_empresa = "Empresa SPED"
    vendas, compras = [], []
    mapa_itens = {} 
    
    for line in content:
        if not line.startswith('|'): continue
        campos = line.split('|')
        reg = campos[1]
        
        if reg == '0000': nome_empresa = campos[6]
        elif reg == '0200':
            mapa_itens[campos[2]] = {'Produto': campos[3], 'NCM': campos[7] if len(campos)>7 else ""}
        elif reg == 'C170':
            cfop = campos[11]
            if cfop not in ['5929', '6929']: # Ignora nota de cupom para não duplicar
                cod = campos[3]
                dados = mapa_itens.get(cod, {'Produto': f'Item {cod}', 'NCM': ''})
                item = {
                    'Chave NFe': 'SPED (Item)', 'CFOP': cfop,
                    'Valor': float(campos[7].replace(',', '.')),
                    'Produto': dados['Produto'], 'NCM': dados['NCM'],
                    'vICMS': float(campos[15].replace(',', '.')) if len(campos)>15 and campos[15] else 0.0,
                    'vPIS': float(campos[25].replace(',', '.')) if len(campos)>25 and campos[25] else 0.0,
                    'vCOFINS': float(campos[31].replace(',', '.')) if len(campos)>31 and campos[31] else 0.0
                }
                if cfop[0] in ['1','2','3']: compras.append(item)
                elif cfop[0] in ['5','6','7']: vendas.append(item)
                
    return nome_empresa, vendas, compras

# --- 3. CLASSIFICADOR HÍBRIDO (A CORREÇÃO) ---
def classificar_item(row, mapa_lei, df_regras, df_tipi, aliq_ibs, aliq_cbs):
    # Normaliza NCM (remove pontos)
    ncm = str(row['NCM']).replace('.', '').strip()
    cfop = str(row['CFOP']).replace('.', '').strip()
    
    # === CAMADA 1: NCM (Base Legal / Regras) ===
    # Procura o NCM no DataFrame de Regras carregado
    # Assume que mapa_lei é um DataFrame com colunas ['NCM', 'cClass', 'Descricao', 'Redutor']
    
    regra_ncm = None
    
    # Verifica se mapa_lei é um DataFrame e não está vazio
    if isinstance(mapa_lei, pd.DataFrame) and not mapa_lei.empty:
        # Tenta achar o NCM exato
        filtro = mapa_lei[mapa_lei['NCM'].astype(str).str.replace('.', '') == ncm]
        if not filtro.empty:
            regra_ncm = filtro.iloc[0]
            
    # Define valores baseados na busca do NCM
    if regra_ncm is not None:
        cClass = str(regra_ncm['cClass'])
        desc_regra = str(regra_ncm.get('Descricao', 'Regra Específica'))
        # Tenta pegar o status, se não tiver, infere pelo cClass ou Redutor
        status = str(regra_ncm.get('Status', 'DIFERENCIADA')) 
        
        # Redutor: 0.0 = Isento, 0.4 = Paga 40%, 1.0 = Paga 100%
        # Se sua base tem a coluna 'Redutor', usa ela. Senão, tenta inferir.
        redutor = float(regra_ncm.get('Redutor', 1.0))
        if 'cesta' in desc_regra.lower(): redutor = 0.0 # Força zero para cesta se a descrição bater
            
        origem_legal = f"Base NCM ({ncm})"
        novo_cst = '20' if redutor < 1.0 else '01'
        if redutor == 0.0: novo_cst = '40'
        
    else:
        # NCM NÃO ENCONTRADO NA BASE -> PADRÃO
        cClass = '000001'
        desc_regra = 'Tributação Padrão'
        status = 'PADRAO'
        redutor = 1.0
        origem_legal = 'NCM não mapeado'
        novo_cst = '01'

    # === CAMADA 2: CFOP (Override / Sobrescrita) ===
    # CFOPs que ZERAM o imposto independente do NCM
    # Removidos 5949/6949 conforme solicitado
    cfops_nao_onerosos = [
        '1910', '2910', '5910', '6910', # Bonificação/Doação
        '1911', '2911', '5911', '6911', # Amostra Grátis
        '5912', '6912', '5913', '6913', # Demonstração
        '5901', '6901', '5902', '6902', # Industrialização
        '5903', '6903', 
        '5915', '6915', '5916', '6916'  # Conserto
    ]
    
    if cfop in cfops_nao_onerosos:
        cClass = '410999'
        desc_regra = f"Op. Não Onerosa (CFOP {cfop})"
        status = 'ZERO (CFOP)'
        redutor = 0.0 # ZERA O IMPOSTO AQUI
        origem_legal = 'Regra de CFOP'
        novo_cst = '410'

    # === CÁLCULOS ===
    # Validação TIPI
    validacao_tipi = "N/A"
    if isinstance(df_tipi, pd.DataFrame) and not df_tipi.empty:
        # Tenta achar o NCM na primeira coluna da TIPI
        if df_tipi.iloc[:, 0].astype(str).str.replace('.', '').str.contains(ncm).any():
            validacao_tipi = "✅ TIPI OK"
        else:
            validacao_tipi = "⚠️ NCM Antigo/Inválido"

    carga_atual = row.get('vICMS', 0) + row.get('vPIS', 0) + row.get('vCOFINS', 0)
    valor_base = row['Valor']
    
    v_ibs = valor_base * aliq_ibs * redutor
    v_cbs = valor_base * aliq_cbs * redutor
    carga_projetada = v_ibs + v_cbs
    
    return [cClass, desc_regra, status, novo_cst, origem_legal, validacao_tipi, carga_atual, carga_projetada, v_ibs, v_cbs]
