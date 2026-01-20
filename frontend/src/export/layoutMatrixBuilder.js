import { flattenTree } from './hierarchyExtractor';

export const buildMatrixLayout = (data, scope, rootNodeId) => {
    // 1. Identificar nó raiz
    let rootNode = data[0];
    // Se o escopo for "subtree" e temos uma árvore filtrada, o rootNode já é o correto.
    // O flattenTree já lida com a estrutura.

    // 2. Aplanar para lista hierárquica
    const flatData = flattenTree(data);

    if (flatData.length === 0) return [];

    const pages = [];
    const CARDS_PER_PAGE = 8;

    // 3. Página 1: Líder / Contexto
    // O primeiro item é sempre o "root" da exportação (seja CEO ou Gerente selecionado)
    const leader = flatData[0];

    // Criar páginas subsequentes
    // Estratégia: Agrupar por páginas de até 8 itens.
    // Podemos apenas paginar a lista linear, pois o requisito pede "matriz horizontal"
    // mas a estrutura de dados é linear. Vamos criar uma representação visual onde
    // cada página tem um título e um grid de cards.

    // Remover o líder da lista de grid se ele já for destaque na capa?
    // Requisito: "Página 1: Card do nó selecionado... Páginas seguintes: Subordinados"

    const subordinates = flatData.slice(1);

    // Página 1 (Capa/Líder)
    pages.push({
        type: 'cover',
        title: leader.department || 'Departamento',
        subtitle: leader.title || 'Cargo',
        leader: leader
    });

    // Páginas de Subordinados
    for (let i = 0; i < subordinates.length; i += CARDS_PER_PAGE) {
        const chunk = subordinates.slice(i, i + CARDS_PER_PAGE);
        pages.push({
            type: 'grid',
            title: `Equipe - ${leader.name}`,
            items: chunk
        });
    }

    return pages;
};
