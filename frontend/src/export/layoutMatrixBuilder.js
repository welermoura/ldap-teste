import { extractLevels } from './hierarchyExtractor';

export const buildMatrixLayout = (data) => {
    if (!data || data.length === 0) return [];

    const rootNode = data[0];
    const levelsMap = extractLevels(rootNode);

    // Configuração do layout (Unidades abstratas, baseadas em proporção A4 Landscape / 16:9)
    // Largura total útil ~10-11 unidades. Altura útil ~6-7 unidades.
    const MAX_CARDS_PER_ROW = 6;
    const MAX_ROWS_PER_PAGE = 4;

    const pages = [];
    let currentPage = {
        title: rootNode.department || 'Organograma',
        subtitle: rootNode.title || 'Visão Hierárquica',
        rows: []
    };

    // Iterar pelos níveis (0, 1, 2...)
    // Ordenar chaves para garantir ordem 0 -> N
    const sortedLevels = Array.from(levelsMap.keys()).sort((a, b) => a - b);

    for (const level of sortedLevels) {
        const nodes = levelsMap.get(level);

        // Se o nível tem muitos nós, quebrar em múltiplas linhas (wraps)
        for (let i = 0; i < nodes.length; i += MAX_CARDS_PER_ROW) {
            const rowNodes = nodes.slice(i, i + MAX_CARDS_PER_ROW);

            // Verificar se cabe na página atual
            if (currentPage.rows.length >= MAX_ROWS_PER_PAGE) {
                pages.push(currentPage);
                currentPage = {
                    title: `${rootNode.department} (Cont.)`,
                    subtitle: `Nível ${level} - Continuação`,
                    rows: []
                };
            }

            // Adicionar linha
            currentPage.rows.push({
                level: level,
                items: rowNodes
            });
        }
    }

    // Adicionar última página se tiver conteúdo
    if (currentPage.rows.length > 0) {
        pages.push(currentPage);
    }

    return pages;
};
