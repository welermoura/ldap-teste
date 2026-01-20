
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

    // Se escopo for 'single' (apenas nó), retorna o nó sem filhos
    if (scope === 'single' && targetId) {
        const node = findNode(data, targetId);
        if (node) {
            // Retorna cópia rasa sem filhos
            return [{ ...node, children: [] }];
        }
        return [];
    }

    return data; // Fallback
};

// Aplanar árvore para lista (útil para PDF lista/diretório)
export const flattenTree = (nodes, depth = 0, result = []) => {
    if (!nodes) return result;
    nodes.forEach(node => {
        result.push({ ...node, depth });
        if (node.children) {
            flattenTree(node.children, depth + 1, result);
        }
    });
    return result;
};
