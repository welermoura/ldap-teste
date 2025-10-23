import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import './ADTree.css';

// Define os tipos de itens para o drag-and-drop
const ItemTypes = {
  AD_OBJECT: 'ad_object',
};

// Componente para um item arrastável no painel de conteúdo
const DraggableItem = ({ member, getIcon }) => {
    const [{ isDragging }, drag] = useDrag(() => ({
        type: ItemTypes.AD_OBJECT,
        item: { dn: member.dn, name: member.name, type: member.type },
        collect: (monitor) => ({
            isDragging: !!monitor.isDragging(),
        }),
    }));

    return (
        <li
            ref={drag}
            className="member-item"
            style={{ opacity: isDragging ? 0.5 : 1 }}
        >
            {getIcon(member.type)}
            <span className="member-name">{member.name}</span>
        </li>
    );
};

// Painel para exibir o conteúdo da OU selecionada
const ContentPanel = ({ selectedNode, members, getIcon }) => {
    if (!selectedNode) {
        return (
            <div className="content-panel">
                <div className="content-placeholder">
                    Selecione uma Unidade Organizacional na árvore para ver seu conteúdo.
                </div>
            </div>
        );
    }

    return (
        <div className="content-panel">
            <h4 className="content-header">Conteúdo de: {selectedNode.text || selectedNode.name}</h4>
            <ul className="member-list">
                {members.map(member => (
                    // Renderiza apenas usuários e grupos como arrastáveis
                    (member.type === 'user' || member.type === 'group')
                        ? <DraggableItem key={member.dn} member={member} getIcon={getIcon} />
                        : <li key={member.dn} className="member-item non-draggable">
                            {getIcon(member.type)}
                            <span className="member-name">{member.name}</span>
                          </li>
                ))}
            </ul>
        </div>
    );
};

// O componente de nó da árvore, agora com capacidade de 'drop'
const TreeNode = ({ node, onNodeClick, onMoveObject }) => {
    const [isOpen, setIsOpen] = useState(false);
    // Os filhos agora são passados como prop para permitir o gerenciamento de estado centralizado
    const children = node.nodes || [];

    const [{ isOver, canDrop }, drop] = useDrop(() => ({
        accept: ItemTypes.AD_OBJECT,
        drop: (item) => {
            // Ação de drop agora chama a função centralizada
            onMoveObject(item, node);
        },
        canDrop: (item) => item.type !== 'ou' && !item.dn.endsWith(node.dn),
        collect: (monitor) => ({
            isOver: !!monitor.isOver(),
            canDrop: !!monitor.canDrop(),
        }),
    }), [node, onMoveObject]);

    const handleNodeClick = () => {
        setIsOpen(!isOpen);
        // A busca de membros agora é tratada no clique se os filhos não estiverem carregados
        onNodeClick(node, !isOpen);
    };

    const getIcon = (type) => {
        switch (type) {
            case 'ou': return <i className="fas fa-folder"></i>;
            case 'user': return <i className="fas fa-user"></i>;
            case 'group': return <i className="fas fa-users"></i>;
            default: return <i className="fas fa-file"></i>;
        }
    };

    return (
        <div ref={drop} className={`tree-node ${isOver && canDrop ? 'drop-target-highlight' : ''}`}>
            <div onClick={handleNodeClick} className="node-label">
                {getIcon('ou')} {node.text}
            </div>
            {isOpen && (
                <div className="node-children">
                    {children.map(child => (
                        <TreeNode key={child.dn} node={child} onNodeClick={onNodeClick} onMoveObject={onMoveObject} />
                    ))}
                </div>
            )}
        </div>
    );
};


// Componente principal da página
const ADExplorerPage = () => {
    const [treeData, setTreeData] = useState([]);
    const [selectedNode, setSelectedNode] = useState(null);
    const [members, setMembers] = useState([]);

    // Função recursiva para encontrar e atualizar um nó na árvore
    const findAndUpdateNode = useCallback((nodes, dn, updateCallback) => {
        return nodes.map(node => {
            if (node.dn === dn) {
                return updateCallback(node);
            }
            if (node.nodes) {
                return { ...node, nodes: findAndUpdateNode(node.nodes, dn, updateCallback) };
            }
            return node;
        });
    }, []);

    const handleNodeClick = useCallback((node, isOpen) => {
        setSelectedNode(node);
        // Busca os membros do nó clicado (OUs e outros objetos)
        axios.get(`/api/ou_members/${encodeURIComponent(node.dn)}`)
            .then(response => {
                setMembers(response.data);
                // Se o nó foi aberto e ainda não tem filhos OUs carregados, atualiza a árvore
                if (isOpen && (!node.nodes || node.nodes.length === 0)) {
                    const ouChildren = response.data.filter(m => m.type === 'ou');
                    setTreeData(prevTree => findAndUpdateNode(prevTree, node.dn, n => ({ ...n, nodes: ouChildren })));
                }
            })
            .catch(error => console.error(`Erro ao buscar membros para ${node.dn}:`, error));
    }, [findAndUpdateNode]);

    const handleMoveObject = useCallback((item, targetNode) => {
        const sourceOuDn = item.dn.substring(item.dn.indexOf(',') + 1);

        // Evita mover para a mesma OU
        if (sourceOuDn === targetNode.dn) return;

        axios.post('/api/move_object', {
            object_dn: item.dn,
            target_ou_dn: targetNode.dn,
        })
        .then(response => {
            if (response.data.success) {
                // Atualização Otimista da Interface
                // 1. Remove o membro da lista da OU selecionada (se for a origem)
                if (selectedNode && selectedNode.dn === sourceOuDn) {
                    setMembers(prevMembers => prevMembers.filter(m => m.dn !== item.dn));
                }
                // 2. Adiciona o membro à lista da OU selecionada (se for o destino)
                 if (selectedNode && selectedNode.dn === targetNode.dn) {
                    const newDn = `${item.dn.split(',')[0]},${targetNode.dn}`;
                    const movedItem = { ...item, dn: newDn };
                    setMembers(prevMembers => [...prevMembers, movedItem].sort((a, b) => a.name.localeCompare(b.name)));
                }
            } else {
                alert('Falha ao mover o objeto: ' + (response.data.error || 'Erro desconhecido.'));
            }
        })
        .catch(error => {
            const errorMessage = error.response?.data?.error || 'Ocorreu um erro de comunicação.';
            alert(errorMessage);
        });
    }, [selectedNode]);

    useEffect(() => {
        axios.get('/api/ous')
          .then(response => setTreeData(response.data))
          .catch(error => console.error("Error fetching OUs:", error));
    }, []);

    const getIcon = (type) => {
        switch (type) {
            case 'ou': return <i className="fas fa-folder"></i>;
            case 'user': return <i className="fas fa-user"></i>;
            case 'group': return <i className="fas fa-users"></i>;
            default: return <i className="fas fa-file"></i>;
        }
    };

    return (
        <DndProvider backend={HTML5Backend}>
            <div className="ad-explorer-container">
                <div className="panels-container">
                    <div className="tree-panel">
                        {treeData.map(rootNode => (
                            <TreeNode key={rootNode.dn} node={rootNode} onNodeClick={handleNodeClick} onMoveObject={handleMoveObject} />
                        ))}
                    </div>
                    <ContentPanel selectedNode={selectedNode} members={members} getIcon={getIcon} />
                </div>
            </div>
        </DndProvider>
    );
};

export default ADExplorerPage;
