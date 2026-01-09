import pandas as pd
import json
import xml.etree.ElementTree as ET

# --- CARREGAMENTO DE DADOS ---
def carregar_base_legal():
    # Simulação de uma tabela de NCMs com regras tributárias
    # Na vida real, isso viria de um CSV ou Banco de Dados
    # Estrutura: NCM : {Regra, Alíquota, Benefício}
    return {
        "00000000": {"regra": "PADRAO", "desc": "Item Genérico"},
        # Adicione aqui NCMs específicos se quiser testar exceções manuais
    }

def carregar_json_regras():
    # Simulação do JSON de regras da Reforma (Tabela CBS/IBS)
    # Aqui entrariam as regras de Cesta Básica, Monofásicos, etc.
    return pd.DataFrame([
        {"cClass": "000001", "Descricao": "Tributação Padrão", "Aliquota": "Cheia"},
        {"cClass": "410999", "Descricao": "Operação Não Onerosa / Imune / Isenta", "Aliquota": "Zero"},
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

# --- PROCESSAMENTO XML (PARSER) ---
def extrair_nome_empresa_xml(tree, ns):
    try:
        emit = tree.find('.//ns:emit', ns)
        return emit.find('ns:xNome', ns).text
    except:
        return "Empresa Desconhecida"

def processar_xml_detalhado(tree, ns, tipo_arquivo):
    itens = []
    
    # Dados da Nota
    try:
        infNFe = tree.find('.//ns:infNFe', ns)
        chave = infNFe.attrib.get('Id', '')[3:] # Remove 'NFe' do início
        ide = infNFe.find('ns:ide', ns)
        natOp = ide.find('ns:natOp', ns).text
    except:
        return []

    # Itens
    for det in infNFe.findall('ns:det', ns):
        prod = det.find('ns:prod', ns)
        imposto = det.find('ns:imposto', ns)
        
        # Extração Básica
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
        
        # Extração Tributária (ICMS/PIS/COFINS) para Comparação
        # Tenta pegar valores de tags comuns (pode variar por CST)
        try:
            icms = imposto.find('.//ns:ICMS', ns)
            # Pega o primeiro filho (ICMS00, ICMS20, etc)
            tags_icms = icms[0] if len(icms) > 0 else None
            item['vICMS'] = float(tags_icms.find('ns:vICMS', ns).text) if tags_icms is not None and tags_icms.find('ns:vICMS', ns) is not None else 0.0
        except: item['vICMS'] = 0.0
            
        try:
            pis = imposto.find('.//ns:PIS', ns)
            tags_pis = pis[0] if len(pis) > 0 else None
            item['vPIS'] = float(tags_pis.find('ns:vPIS', ns).text) if tags_pis is not None and tags_pis.find('ns:vPIS', ns) is not None else 0.0
        except: item['vPIS'] = 0.0
            
        try:
            cofins = imposto.find('.//ns:COFINS', ns)
            tags_cofins = cofins[0] if len(cofins) > 0 else None
            item['vCOFINS'] = float(tags_cofins.find('ns:vCOFINS', ns).text) if tags_cofins is not None and tags_cofins.find('ns:vCOFINS', ns) is not None else 0.0
        except: item['vCOFINS'] = 0.0
        
        itens.append(item)
        
    return itens

# --- PROCESSAMENTO SPED (TXT) ---
def processar_sped_fiscal(file_obj):
    # Lendo o arquivo em memória
    content = file_obj.getvalue().decode('latin1').splitlines()
    
    nome_empresa = "Empresa SPED"
    vendas = []
    compras = []
    
    # Mapeamento rápido de itens (0200) para pegar descrição e NCM
    # Chave: Cod_Item_SPED -> {Descricao, NCM}
    mapa_itens = {} 
    
    for line in content:
        if not line.startswith('|'): continue
        campos = line.split('|')
        registro = campos[1]
        
        if registro == '0000':
            nome_empresa = campos[6]
            
        elif registro == '0200':
            # |0200|COD_ITEM|DESCR_ITEM|COD_BARRA|COD_ANT_ITEM|UNID_INV|TIPO_ITEM|COD_NCM|...
            cod_item = campos[2]
            descr = campos[3]
            ncm = campos[7] if len(campos) > 7 else ""
            mapa_itens[cod_item] = {'Produto': descr, 'NCM': ncm}
            
        elif registro in ['C100', 'C190']: # Notas Fiscais (Simplificado)
            # Para uma auditoria completa, precisaríamos cruzar C100 (Cabeçalho) com C170 (Itens)
            # Como o C170 é filho, a lógica é complexa para um script simples.
            # Vamos focar em extrair totais ou, se possível, itens do C170 se o arquivo tiver.
            pass
            
        elif registro == 'C170': # Itens da Nota
            # |C170|NUM_ITEM|COD_ITEM|DESCR_COMPL|QTD|UNID|VL_ITEM|VL_DESC|...|CFOP|COD_NAT|...
            # Precisaríamos do Pai (C100) para saber se é entrada ou saída e a Chave.
            # Simplificação: Vamos assumir CFOP
            cfop = campos[11]
            cod_item = campos[3]
            valor = float(campos[7].replace(',', '.'))
            
            dados_prod = mapa_itens.get(cod_item, {'Produto': 'Item ' + cod_item, 'NCM': ''})
            
            item = {
                'Chave NFe': 'SPED (S/ Chave Link)', # C170 não tem a chave direto na linha
                'CFOP': cfop,
                'Valor': valor,
                'Produto': dados_prod['Produto'],
                'NCM': dados_prod['NCM'],
                'vICMS': float(campos[15].replace(',', '.')) if len(campos) > 15 and campos[15] else 0.0,
                'vPIS': float(campos[25].replace(',', '.')) if len(campos) > 25 and campos[25] else 0.0,
                'vCOFINS': float(campos[31].replace(',', '.')) if len(campos) > 31 and campos[31] else 0.0
            }
            
            if cfop.startswith('1') or cfop.startswith('2') or cfop.startswith('3'):
                compras.append(item)
            elif cfop.startswith('5') or cfop.startswith('6') or cfop.startswith('7'):
                vendas.append(item)

    return nome_empresa, vendas, compras

# --- MOTOR DE REGRAS TRIBUTÁRIAS (A MÁGICA) ---
def classificar_item(row, mapa_lei, df_regras, df_tipi, aliq_ibs, aliq_cbs):
    ncm = str(row['NCM']).replace('.', '').strip()
    cfop = str(row['CFOP']).strip()
    
    # -------------------------------------------------------------------------
    # 1. REGRA DE OURO: CFOP DE OPERAÇÃO NÃO ONEROSA (Substitui NCM)
    # -------------------------------------------------------------------------
    # Lista de CFOPs comuns para Brindes, Amostras, Doações, Bonificações
    cfops_nao_onerosos = [
        '1910', '2910', '5910', '6910', # Bonificação, doação ou brinde
        '1911', '2911', '5911', '6911', # Amostra grátis
        '5912', '6912',                 # Amostra grátis (Demonstração - suspensão)
        '5913', '6913',                 # Retorno de amostra ou demonstração
    ]
    
    if cfop in cfops_nao_onerosos:
        # Força classificação de "Não Oneroso"
        return [
            '410999',                       # cClassTrib (Código para não tributado/genérico isento)
            'Operação Não Onerosa (CFOP)',  # DescRegra
            'ZERO (ISENTO/IMUNE)',          # Status
            '410',                          # Novo CST (Sugerido para não tributado)
            'CFOP não oneroso',             # Origem Legal
            'Ignorado (Regra CFOP)',        # Validação TIPI
            0.0,                            # Carga Atual (Consideramos zero para efeito de comparação)
            0.0,                            # Carga Projetada (IBS/CBS Zero)
            0.0,                            # vIBS
            0.0                             # vCBS
        ]

    # -------------------------------------------------------------------------
    # 2. FLUXO NORMAL (POR NCM) SE NÃO FOR NÃO ONEROSO
    # -------------------------------------------------------------------------
    
    # Lógica padrão (Simulada)
    # Se o NCM estiver na lista de Cesta Básica (exemplo hipotético)
    ncms_cesta_basica = ['10063021', '07133319', '04012010'] # Arroz, Feijão, Leite
    
    if ncm in ncms_cesta_basica:
        cClass = '100001' # Exemplo Cesta Básica
        desc = 'Cesta Básica Nacional'
        status = 'ZERO'
        novo_cst = '20' # Exemplo
        origem = 'LC 2024 - Cesta Básica'
        redutor = 0.0 # Alíquota Zero
    else:
        cClass = '000001' # Padrão
        desc = 'Tributação Padrão'
        status = 'PADRAO'
        novo_cst = '01'
        origem = 'Regra Geral'
        redutor = 1.0 # 100% da alíquota
    
    # Validação TIPI (Se carregada)
    validacao_tipi = "N/A"
    if not df_tipi.empty:
        # Tenta achar o NCM na TIPI
        if ncm in df_tipi.values: validacao_tipi = "✅ NCM Existe na TIPI"
        else: validacao_tipi = "⚠️ NCM Não Encontrado (Obsoleto?)"

    # Cálculo da Carga
    carga_atual = row.get('vICMS', 0) + row.get('vPIS', 0) + row.get('vCOFINS', 0)
    
    valor_base = row['Valor']
    v_ibs = valor_base * aliq_ibs * redutor
    v_cbs = valor_base * aliq_cbs * redutor
    carga_projetada = v_ibs + v_cbs
    
    return [cClass, desc, status, novo_cst, origem, validacao_tipi, carga_atual, carga_projetada, v_ibs, v_cbs]
