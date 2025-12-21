from fpdf import FPDF
from datetime import datetime
import pandas as pd

class PDFAuditoria(FPDF):
    def __init__(self, empresa):
        super().__init__()
        self.empresa = empresa
        self.data_emissao = datetime.now().strftime("%d/%m/%Y")

    def header(self):
        # Cabeçalho da PÁGINA (Logo/Título)
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, 'Laudo Técnico de Auditoria Fiscal', ln=True, align='C')
        
        self.set_font('Helvetica', 'I', 10)
        self.set_text_color(127, 140, 141)
        self.cell(0, 5, f'Preparado para: {self.empresa}', ln=True, align='C')
        self.cell(0, 5, f'Data de Emissão: {self.data_emissao}', ln=True, align='C')
        self.ln(5)
        
        self.set_draw_color(230, 126, 34)
        self.set_line_width(1)
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}} - Gerado por cClass Auditor AI', align='C')

    def chapter_title(self, label):
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(0)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 10, f'  {label}', ln=True, fill=True)
        self.ln(4)

    def card_resumo(self, debito, credito, saldo):
        self.set_font('Helvetica', '', 10)
        
        self.set_fill_color(255, 255, 255)
        self.cell(60, 10, "Débitos Estimados (Vendas):", border=1)
        self.set_font('Helvetica', 'B', 10)
        self.cell(0, 10, f"R$ {debito:,.2f}", border=1, ln=True)
        
        self.set_font('Helvetica', '', 10)
        self.cell(60, 10, "Créditos Estimados (Compras):", border=1)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(39, 174, 96)
        self.cell(0, 10, f"R$ {credito:,.2f}", border=1, ln=True)
        self.set_text_color(0)
        
        self.set_font('Helvetica', 'B', 10)
        self.cell(60, 10, "Saldo Final (IBS/CBS):", border=1)
        
        cor_saldo = (192, 57, 43) if saldo > 0 else (39, 174, 96)
        self.set_text_color(*cor_saldo)
        tipo = "A PAGAR" if saldo > 0 else "CREDOR"
        self.cell(0, 10, f"R$ {abs(saldo):,.2f} ({tipo})", border=1, ln=True)
        self.set_text_color(0)
        self.ln(10)

    def _imprimir_cabecalho_tabela(self):
        """Método auxiliar para desenhar o cabeçalho da tabela"""
        self.set_font('Helvetica', 'B', 7)
        self.set_fill_color(230, 126, 34) # Laranja
        self.set_text_color(255) # Branco
        
        # Definição das Larguras (Total ~190mm)
        # Cód(18) | Prod(57) | NCM(18) | CST(10) | cClass(17) | Val(35) | Imp(35)
        
        self.cell(18, 7, 'Cód.', 1, 0, 'C', True)
        self.cell(57, 7, 'Produto', 1, 0, 'C', True)
        self.cell(18, 7, 'NCM', 1, 0, 'C', True)
        self.cell(10, 7, 'CST', 1, 0, 'C', True)
        self.cell(17, 7, 'cClass', 1, 0, 'C', True) # Nova Coluna
        self.cell(35, 7, 'Valor Base', 1, 0, 'C', True)
        self.cell(35, 7, 'IBS+CBS', 1, 1, 'C', True)

    def tabela_itens(self, df):
        # Imprime cabeçalho na primeira vez
        self._imprimir_cabecalho_tabela()
        
        self.set_font('Helvetica', '', 6) # Fonte menor para caber tudo
        self.set_text_color(0)
        self.set_fill_color(245, 245, 245)
        
        fill = False
        # Aumentei o limite para 200 itens para testar paginação
        for _, row in df.head(200).iterrows():
            
            # --- LÓGICA DE PAGINAÇÃO ---
            # Se estiver perto do fim da página (270mm), cria nova e repete cabeçalho
            if self.get_y() > 270:
                self.add_page()
                self._imprimir_cabecalho_tabela()
                # Restaura configurações da fonte de dados
                self.set_font('Helvetica', '', 6)
                self.set_text_color(0)
                self.set_fill_color(245, 245, 245)

            # Preparação dos Dados
            cod = str(row.get('Cód. Produto', ''))[:10]
            prod = str(row['Produto'])[:40] # Corta texto longo
            ncm = str(row['NCM'])
            cst = str(row.get('Novo CST', ''))
            cclass = str(row.get('cClassTrib', '')) # Nova Coluna
            val = f"R$ {row.get('Valor', 0):,.2f}"
            imp = f"R$ {row.get('Carga Projetada', 0):,.2f}"
            
            # Desenho da Linha
            self.cell(18, 6, cod, 1, 0, 'C', fill)
            self.cell(57, 6, prod, 1, 0, 'L', fill)
            self.cell(18, 6, ncm, 1, 0, 'C', fill)
            self.cell(10, 6, cst, 1, 0, 'C', fill)
            self.cell(17, 6, cclass, 1, 0, 'C', fill) # Nova Coluna
            self.cell(35, 6, val, 1, 0, 'R', fill)
            self.cell(35, 6, imp, 1, 1, 'R', fill)
            
            fill = not fill # Alterna cor (Zebrado)
            
        self.ln(5)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 5, '* Listagem de itens limitada para otimização do documento.', ln=True)

def gerar_pdf_bytes(empresa, df_vendas, df_compras):
    pdf = PDFAuditoria(empresa)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 1. Resumo
    pdf.chapter_title("1. Resumo Executivo")
    deb = df_vendas['Carga Projetada'].sum() if not df_vendas.empty else 0
    cred = df_compras['Carga Projetada'].sum() if not df_compras.empty else 0
    saldo = deb - cred
    pdf.card_resumo(deb, cred, saldo)
    
    # Colunas necessárias para a nova tabela
    cols = ['Cód. Produto', 'Produto', 'NCM', 'Novo CST', 'cClassTrib', 'Valor', 'Carga Projetada']

    # 2. Vendas
    if not df_vendas.empty:
        pdf.chapter_title("2. Detalhamento de Saídas (Débitos)")
        # Garante que as colunas existem antes de copiar
        cols_v = [c for c in cols if c in df_vendas.columns]
        df_v = df_vendas[cols_v].copy()
        pdf.tabela_itens(df_v)
        
    # 3. Compras
    if not df_compras.empty:
        pdf.add_page()
        pdf.chapter_title("3. Detalhamento de Entradas (Créditos)")
        cols_c = [c for c in cols if c in df_compras.columns]
        df_c = df_compras[cols_c].copy()
        pdf.tabela_itens(df_c)
        
    return bytes(pdf.output())