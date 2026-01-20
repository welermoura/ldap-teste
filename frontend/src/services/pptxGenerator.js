import PptxGenJS from 'pptxgenjs';
import { flattenTree } from '../utils/exportUtils';

export const generatePPTX = async (data, scope) => {
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_16x9';

    // Slide Mestre / Capa
    const slide = pptx.addSlide();
    slide.addText('Organograma Corporativo', { x: 1, y: 1, w: '80%', fontSize: 24, bold: true, color: '363636' });
    slide.addText(`Escopo: ${scope === 'full' ? 'Organização Completa' : 'Área Selecionada'}`, { x: 1, y: 2, fontSize: 14, color: '737373' });
    slide.addText(`Gerado em: ${new Date().toLocaleDateString()}`, { x: 1, y: 2.5, fontSize: 12, color: 'AAAAAA' });

    // Processar dados
    // Estratégia: Listagem hierárquica simples em slides para garantir legibilidade
    // Desenhar árvore complexa em PPTX via JS é propenso a erros de layout.
    // Vamos criar slides por "Departamento" ou apenas uma lista indentada visual.

    const flatData = flattenTree(data);

    // Paginação simples: 10 items por slide
    const itemsPerSlide = 8;
    for (let i = 0; i < flatData.length; i += itemsPerSlide) {
        const slideChunk = flatData.slice(i, i + itemsPerSlide);
        const contentSlide = pptx.addSlide();

        contentSlide.addText('Estrutura Organizacional', { x: 0.5, y: 0.5, fontSize: 18, color: '363636', bold: true });

        let yPos = 1.2;
        slideChunk.forEach((node) => {
            // Indentação visual baseada na profundidade (depth)
            const indent = node.depth * 0.4;

            // Caixa do card
            contentSlide.addShape(pptx.ShapeType.rect, {
                x: 0.5 + indent, y: yPos, w: 4, h: 0.8,
                fill: { color: 'FFFFFF' },
                line: { color: 'E2E8F0', width: 1 },
                shadow: { type: 'outer', color: '000000', opacity: 0.1, blur: 2, offset: 2 }
            });

            // Conector visual (linha vertical/horizontal simulada)
            if (node.depth > 0) {
                 contentSlide.addShape(pptx.ShapeType.line, {
                    x: 0.5 + indent - 0.2, y: yPos + 0.4, w: 0.2, h: 0,
                    line: { color: 'CBD5E1', width: 2 }
                 });
            }

            // Nome
            contentSlide.addText(node.name, {
                x: 0.7 + indent, y: yPos + 0.1, w: 3.5, h: 0.3,
                fontSize: 12, bold: true, color: '1E293B'
            });

            // Cargo / Dept
            contentSlide.addText(`${node.title || 'N/A'} - ${node.department || 'Geral'}`, {
                x: 0.7 + indent, y: yPos + 0.4, w: 3.5, h: 0.3,
                fontSize: 10, color: '64748B'
            });

            yPos += 1.0;
        });

        // Rodapé
        contentSlide.addText(`Página ${Math.floor(i/itemsPerSlide) + 1}`, { x: 12, y: 7, fontSize: 10, color: 'AAAAAA' });
    }

    // Salvar
    await pptx.writeFile({ fileName: `Organograma_${new Date().toISOString().slice(0,10)}.pptx` });
};
