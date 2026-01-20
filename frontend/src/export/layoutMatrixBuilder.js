import { extractLevels } from './hierarchyExtractor';

export const buildMatrixLayout = (data) => {
    if (!data || data.length === 0) return [];

    const rootNode = data[0];
    const levelsMap = extractLevels(rootNode);

    // Configuração do layout
    const MAX_ROWS_PER_PAGE = 4;

    const pages = [];
    let currentPage = {
        title: rootNode.department || 'Organograma',
        subtitle: rootNode.title || 'Visão Hierárquica',
        rows: []
    };

    // Iterar pelos níveis
    const sortedLevels = Array.from(levelsMap.keys()).sort((a, b) => a - b);
    const lastLevelIndex = sortedLevels.length - 1;

    for (let i = 0; i < sortedLevels.length; i++) {
        const level = sortedLevels[i];
        const nodes = levelsMap.get(level);
        const isLastLevel = (i === lastLevelIndex);

        // Lógica de Grid
        // Níveis intermediários: até 8 por linha (quebra em múltiplas linhas se > 8)
        // Último nível: Grid de 3 colunas (quebra em linhas de 3)
        const CARDS_PER_ROW = isLastLevel ? 3 : 8;

        for (let j = 0; j < nodes.length; j += CARDS_PER_ROW) {
            const rowNodes = nodes.slice(j, j + CARDS_PER_ROW);

            // Verificar paginação
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
                items: rowNodes,
                isLastLevel: isLastLevel // Flag para renderizador saber layout (centralizado vs grid 3-col)
            });
        }
    }

    if (currentPage.rows.length > 0) {
        pages.push(currentPage);
    }

    return pages;
};
