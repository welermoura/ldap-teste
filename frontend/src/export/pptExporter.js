import PptxGenJS from 'pptxgenjs';
import { buildMatrixLayout } from './layoutMatrixBuilder';

export const generatePPTX = async (data, scope) => {
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_16x9';

    const pages = buildMatrixLayout(data);

    pages.forEach((pageData) => {
        const slide = pptx.addSlide();

        // Header
        slide.addText(pageData.title, { x: 0.5, y: 0.4, fontSize: 20, bold: true, color: '363636' });
        if (pageData.subtitle) {
            slide.addText(pageData.subtitle, { x: 0.5, y: 0.8, fontSize: 12, color: '737373' });
        }

        // Render Rows (Levels)
        const startY = 1.5;
        const rowHeight = 1.3;
        const cardW = 1.5;
        const cardH = 0.8;
        const gapX = 0.2;

        // Canvas width is roughly 10 inches for 16:9
        const pageWidth = 10;

        pageData.rows.forEach((row, rowIdx) => {
            const itemCount = row.items.length;
            const rowWidth = itemCount * cardW + (itemCount - 1) * gapX;
            const startX = (pageWidth - rowWidth) / 2; // Center row
            const currentY = startY + (rowIdx * rowHeight);

            row.items.forEach((item, itemIdx) => {
                const x = startX + itemIdx * (cardW + gapX);

                // Card Shape
                slide.addShape(pptx.ShapeType.rect, {
                    x: x, y: currentY, w: cardW, h: cardH,
                    fill: { color: 'FFFFFF' },
                    line: { color: 'E2E8F0', width: 1 }
                });

                // Content
                slide.addText(item.name, {
                    x: x + 0.05, y: currentY + 0.1, w: cardW - 0.1, h: 0.3,
                    fontSize: 10, bold: true, color: '0F172A', align: 'center'
                });
                slide.addText(item.title, {
                    x: x + 0.05, y: currentY + 0.4, w: cardW - 0.1, h: 0.2,
                    fontSize: 8, color: '475569', align: 'center'
                });
                slide.addText(item.department, {
                    x: x + 0.05, y: currentY + 0.6, w: cardW - 0.1, h: 0.15,
                    fontSize: 7, color: '94A3B8', align: 'center'
                });
            });
        });

        // Footer
        slide.addText(`Gerado em ${new Date().toLocaleDateString()}`, { x: 8.5, y: 5.2, fontSize: 8, color: 'AAAAAA' });
    });

    await pptx.writeFile({ fileName: `Organograma_${new Date().toISOString().slice(0,10)}.pptx` });
};
