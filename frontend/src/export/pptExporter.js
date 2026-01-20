import PptxGenJS from 'pptxgenjs';
import { buildMatrixLayout } from './layoutMatrixBuilder';

export const generatePPTX = async (data, scope) => {
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_16x9';

    const pages = buildMatrixLayout(data, scope);

    pages.forEach((pageData) => {
        const slide = pptx.addSlide();

        // Header
        slide.addText(pageData.title, { x: 0.5, y: 0.5, fontSize: 24, bold: true, color: '363636' });
        if (pageData.subtitle) {
            slide.addText(pageData.subtitle, { x: 0.5, y: 1.0, fontSize: 14, color: '737373' });
        }

        if (pageData.type === 'cover') {
            // Render Leader Card centered
            const leader = pageData.leader;
            slide.addShape(pptx.ShapeType.rect, {
                x: 4, y: 2.5, w: 5, h: 2.5,
                fill: { color: 'F8FAFC' },
                line: { color: '3B82F6', width: 3 },
                shadow: { type: 'outer', opacity: 0.2 }
            });
            slide.addText(leader.name, {
                x: 4.2, y: 3.0, w: 4.6, fontSize: 20, bold: true, color: '0F172A', align: 'center'
            });
            slide.addText(leader.title, {
                x: 4.2, y: 3.6, w: 4.6, fontSize: 16, color: '475569', align: 'center'
            });
            slide.addText(leader.department, {
                x: 4.2, y: 4.2, w: 4.6, fontSize: 12, color: '94A3B8', align: 'center'
            });

        } else if (pageData.type === 'grid') {
            // Render Grid (2 rows x 4 cols = 8 items max)
            const items = pageData.items;
            const startX = 0.5;
            const startY = 1.5;
            const cardW = 2.8;
            const cardH = 1.2;
            const gapX = 0.2;
            const gapY = 0.4;

            items.forEach((item, index) => {
                const col = index % 4;
                const row = Math.floor(index / 4);

                const x = startX + (col * (cardW + gapX));
                const y = startY + (row * (cardH + gapY));

                slide.addShape(pptx.ShapeType.rect, {
                    x: x, y: y, w: cardW, h: cardH,
                    fill: { color: 'FFFFFF' },
                    line: { color: 'E2E8F0', width: 1 }
                });

                slide.addText(item.name, {
                    x: x + 0.1, y: y + 0.1, w: cardW - 0.2, h: 0.4,
                    fontSize: 11, bold: true, color: '0F172A'
                });
                slide.addText(item.title, {
                    x: x + 0.1, y: y + 0.5, w: cardW - 0.2, h: 0.3,
                    fontSize: 9, color: '475569'
                });
                slide.addText(item.department, {
                    x: x + 0.1, y: y + 0.8, w: cardW - 0.2, h: 0.2,
                    fontSize: 8, color: '94A3B8'
                });
            });
        }

        // Footer
        slide.addText(`Gerado em ${new Date().toLocaleDateString()}`, { x: 11, y: 7, fontSize: 10, color: 'AAAAAA' });
    });

    await pptx.writeFile({ fileName: `Organograma_${new Date().toISOString().slice(0,10)}.pptx` });
};
