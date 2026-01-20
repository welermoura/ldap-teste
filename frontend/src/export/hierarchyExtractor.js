
// Encontrar um nó na árvore pelo ID (distinguishedName)
export const findNode = (nodes, id) => {
    if (!nodes) return null;
    for (const node of nodes) {
        if (node.distinguishedName === id) return node;
        if (node.children) {
            const found = findNode(node.children, id);
            if (found) return found;
        }
    }
    return null;
};

// Filtrar a árvore baseado no escopo selecionado
export const filterTree = (data, scope, targetId) => {
    if (!data || data.length === 0) return [];

    // Se escopo for 'full', retorna a árvore inteira
    if (scope === 'full') {
        return data;
    }

    // Se escopo for 'subtree' (nó + filhos), encontra o nó e retorna como nova raiz
    if (scope === 'subtree' && targetId) {
        const node = findNode(data, targetId);
        return node ? [node] : [];
    }

    return data; // Fallback
};

// Agrupar nós por nível hierárquico (BFS)
export const extractLevels = (rootNode) => {
    const levels = new Map(); // Map<level, Node[]>

    if (!rootNode) return levels;

    const queue = [{ node: rootNode, level: 0 }];

    while (queue.length > 0) {
        const { node, level } = queue.shift();

        if (!levels.has(level)) {
            levels.set(level, []);
        }
        levels.get(level).push(node);

        if (node.children) {
            node.children.forEach(child => {
                queue.push({ node: child, level: level + 1 });
            });
        }
    }

    return levels;
};
