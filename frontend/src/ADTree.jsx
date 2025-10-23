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
const TreeNode = ({ node, onNodeClick, refreshNode }) => {
    const [isOpen, setIsOpen] = useState(false);
    const [children, setChildren] = useState([]);

    const [{ isOver, canDrop }, drop] = useDrop(() => ({
        accept: ItemTypes.AD_OBJECT,
        drop: (item) => {
            // A ação de 'drop' acontece aqui
            axios.post('/api/move_object', {
                object_dn: item.dn,
                target_ou_dn: node.dn,
            })
            .then(response => {
                if (response.data.success) {
                    // Atualiza a OU de origem (pai do item movido) e a de destino
                    const sourceOuDn = item.dn.substring(item.dn.indexOf(',') + 1);
                    refreshNode(sourceOuDn);
                    refreshNode(node.dn);
                } else {
                    alert('Falha ao mover o objeto: ' + response.data.error);
                }
            })
            .catch(error => {
                console.error("Erro ao mover objeto:", error);
                // Exibe a mensagem de erro específica retornada pela API, se disponível
                const errorMessage = error.response?.data?.error || 'Ocorreu um erro de comunicação ao mover o objeto.';
                alert(errorMessage);
            });
        },
        canDrop: (item) => item.type !== 'ou', // OUs não podem ser movidas (por enquanto)
        collect: (monitor) => ({
            isOver: !!monitor.isOver(),
            canDrop: !!monitor.canDrop(),
        }),
    }), [node, refreshNode]); // Dependências do hook

    const handleNodeClick = () => {
        toggleOpen();
        fetchAndDisplayMembers();
    };

    const fetchAndDisplayMembers = useCallback((forceOpen = false) => {
        if ((forceOpen || !isOpen) && children.length === 0) {
            axios.get(`/api/ou_members/${encodeURIComponent(node.dn)}`)
                .then(response => {
                    const allMembers = response.data;
                    const ouChildren = allMembers.filter(member => member.type === 'ou');
                    setChildren(ouChildren);
                    onNodeClick(node, allMembers);
                });
        } else {
             axios.get(`/api/ou_members/${encodeURIComponent(node.dn)}`)
                .then(response => {
                    onNodeClick(node, response.data);
                });
        }
    }, [isOpen, children, node, onNodeClick]);

    const toggleOpen = () => {
        setIsOpen(!isOpen);
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
                {getIcon(node.type)} {node.text || node.name}
            </div>
            {isOpen && (
                <div className="node-children">
                    {children.map(child => (
                        <TreeNode key={child.dn} node={child} onNodeClick={onNodeClick} refreshNode={refreshNode} />
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

    const fetchRootOUs = () => {
        axios.get('/api/ous')
          .then(response => setTreeData(response.data))
          .catch(error => console.error("Error fetching OUs:", error));
    };

    useEffect(() => {
        fetchRootOUs();
    }, []);

    const handleNodeSelection = (node, children) => {
        setSelectedNode(node);
        setMembers(children);
    };

    const refreshNode = useCallback((dn) => {
      // For now, a simple way to refresh is to refetch everything
      // A more optimized approach would be to find the node in the state and refetch its children
      fetchRootOUs();
      if (selectedNode && (selectedNode.dn === dn || dn.endsWith(selectedNode.dn))) {
          axios.get(`/api/ou_members/${encodeURIComponent(dn)}`)
              .then(response => {
                  setMembers(response.data);
              });
      }
    }, [selectedNode]);

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
                            <TreeNode key={rootNode.dn} node={{...rootNode, type: 'ou'}} onNodeClick={handleNodeSelection} refreshNode={refreshNode}/>
                        ))}
                    </div>
                    <ContentPanel selectedNode={selectedNode} members={members} getIcon={getIcon} />
                </div>
            </div>
        </DndProvider>
    );
};

export default ADExplorerPage;
