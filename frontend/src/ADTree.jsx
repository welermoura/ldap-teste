import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import EditUserModal from './EditUserModal';
import DisableTempModal from './DisableTempModal';
import ScheduleAbsenceModal from './ScheduleAbsenceModal';
import './ADTree.css';

// Define os tipos de itens para o drag-and-drop
const ItemTypes = {
  AD_OBJECT: 'ad_object',
};

// Componente para um item arrastável no painel de conteúdo
const DraggableItem = ({ member, getIcon, onContextMenu }) => {
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
            onContextMenu={(e) => onContextMenu(e, member)}
        >
            {getIcon(member.type)}
            <div className="member-info">
                <span className="member-name">{member.name}</span>
                {member.ou_path && <span className="member-ou-path">{member.ou_path}</span>}
            </div>
        </li>
    );
};

// Componente para o Menu de Contexto (Reconstruído)
const ContextMenu = ({ x, y, show, onClose, targetNode, permissions, onEdit, onToggleStatus, onResetPassword, onDelete, onDisableTemp, onScheduleAbsence }) => {
    if (!show || !targetNode) return null;

    const style = { top: y, left: x };
    const isUser = targetNode.type === 'user';
    const isComputer = targetNode.type === 'computer';

    const renderMenuItem = (key, icon, text, action, condition) => {
        if (!condition) return null;
        return <li key={key} onClick={() => { action(targetNode); onClose(); }}><i className={`fas ${icon} me-2`}></i>{text}</li>;
    };

    const userActions = [
        renderMenuItem('edit', 'fa-user-edit', 'Editar', onEdit, permissions.can_edit),
        renderMenuItem('toggle', 'fa-ban', 'Ativar/Desativar Conta', onToggleStatus, permissions.can_disable),
        renderMenuItem('reset_password', 'fa-key', 'Resetar Senha', onResetPassword, permissions.can_reset_password),
        renderMenuItem('disable_temp', 'fa-user-clock', 'Desativar por X dias', onDisableTemp, permissions.can_disable),
        renderMenuItem('schedule_absence', 'fa-calendar-alt', 'Agendar Ausência', onScheduleAbsence, permissions.can_disable),
    ];

    const computerActions = [
        renderMenuItem('delete_computer', 'fa-trash-alt', 'Excluir', onDelete, permissions.can_delete_user),
    ];

    // Filtra ações nulas para a linha separadora
    const visibleUserActions = userActions.filter(Boolean);

    return (
        <div className="context-menu" style={style} onMouseLeave={onClose}>
            <ul>
                {isUser && visibleUserActions}
                {isComputer && computerActions}

                {/* Separador e Excluir para Usuários */}
                {isUser && permissions.can_delete_user && visibleUserActions.length > 0 && <li className="separator"></li>}
                {isUser && renderMenuItem('delete_user', 'fa-trash-alt', 'Excluir', onDelete, permissions.can_delete_user)}
            </ul>
        </div>
    );
};

// Painel para exibir o conteúdo da OU selecionada ou os resultados da busca
const ContentPanel = ({ selectedNode, members, getIcon, onOuDoubleClick, isSearchMode, onContextMenu }) => {
    const hasMembers = members && members.length > 0;

    // Mensagem para quando a busca não retorna resultados
    if (isSearchMode && !hasMembers) {
        return (
            <div className="content-panel">
                <h4 className="content-header">Resultados da Busca</h4>
                <div className="content-placeholder">
                    Nenhum usuário ou computador encontrado.
                </div>
            </div>
        );
    }

    // Mensagem para quando uma OU é selecionada mas não tem conteúdo
    if (!isSearchMode && selectedNode && !hasMembers) {
        return (
            <div className="content-panel">
                <h4 className="content-header">Conteúdo de: {selectedNode.text || selectedNode.name}</h4>
                <div className="content-placeholder">
                    Esta Unidade Organizacional está vazia.
                </div>
            </div>
        );
    }

    // Mensagem inicial antes de qualquer seleção ou busca
    if (!isSearchMode && !selectedNode) {
        return (
            <div className="content-panel">
                <div className="content-placeholder">
                    Selecione uma Unidade Organizacional na árvore para ver seu conteúdo.
                </div>
            </div>
        );
    }

    const headerText = isSearchMode ? "Resultados da Busca" : `Conteúdo de: ${selectedNode.text || selectedNode.name}`;

    return (
        <div className="content-panel">
            <h4 className="content-header">{headerText}</h4>
            <ul className="member-list">
                {members.map(member => {
                    // Na busca, todos os itens são arrastáveis (se forem user/computer)
                    if (isSearchMode && (member.type === 'user' || member.type === 'computer')) {
                        return <DraggableItem key={member.dn} member={member} getIcon={getIcon} onContextMenu={onContextMenu} />;
                    }
                    // Comportamento normal para visualização de OU
                    if (!isSearchMode && (member.type === 'user' || member.type === 'group' || member.type === 'computer')) {
                        return <DraggableItem key={member.dn} member={member} getIcon={getIcon} onContextMenu={onContextMenu} />;
                    } else if (!isSearchMode && member.type === 'ou') {
                        return (
                            <li key={member.dn} className="member-item non-draggable" onDoubleClick={() => onOuDoubleClick(member)} style={{ cursor: 'pointer' }} onContextMenu={(e) => onContextMenu(e, member)}>
                                {getIcon(member.type)}
                                <span className="member-name">{member.name}</span>
                            </li>
                        );
                    } else {
                        return (
                            <li key={member.dn} className="member-item non-draggable">
                                {getIcon(member.type)}
                                <span className="member-name">{member.name}</span>
                            </li>
                        );
                    }
                })}
            </ul>
        </div>
    );
};

// O componente de nó da árvore, agora com capacidade de 'drop'
const TreeNode = ({ node, onNodeClick, onMoveObject, onContextMenu }) => {
    const [isOpen, setIsOpen] = useState(false);
    // Os filhos agora são passados como prop para permitir o gerenciamento de estado centralizado
    const children = node.nodes || [];

    const [{ isOver, canDrop }, drop] = useDrop(() => ({
        accept: ItemTypes.AD_OBJECT,
        drop: (item) => {
            // Ação de drop agora chama a função centralizada
            onMoveObject(item, node);
        },
        canDrop: (item) => item.type !== 'ou', // Permite dropar em qualquer OU, incluindo a atual
        collect: (monitor) => ({
            isOver: !!monitor.isOver({ shallow: true }),
            canDrop: !!monitor.canDrop(),
        }),
    }), [node, onMoveObject]);

    useEffect(() => {
        let timer = null;
        if (isOver && canDrop && !isOpen) {
            // Inicia um temporizador para expandir a OU
            timer = setTimeout(() => {
                setIsOpen(true);
                onNodeClick(node, true); // Chama a função para buscar os filhos
            }, 500); // Atraso de 500ms
        }

        // Função de limpeza para cancelar o temporizador se o mouse sair
        return () => {
            if (timer) {
                clearTimeout(timer);
            }
        };
    }, [isOver, canDrop, isOpen, onNodeClick, node]);

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
            case 'computer': return <i className="fas fa-desktop"></i>;
            default: return <i className="fas fa-file"></i>;
        }
    };

    return (
        <div ref={drop} className={`tree-node ${isOver && canDrop ? 'drop-target-highlight' : ''}`}>
            <div onClick={handleNodeClick} className="node-label" onContextMenu={(e) => onContextMenu(e, node)}>
                {getIcon('ou')} {node.text}
            </div>
            {isOpen && (
                <div className="node-children">
                    {children.map(child => (
                        <TreeNode key={child.dn} node={child} onNodeClick={onNodeClick} onMoveObject={onMoveObject} onContextMenu={onContextMenu} />
                    ))}
                </div>
            )}
        </div>
    );
};

// Componente para o Modal de Confirmação
const ConfirmationModal = ({ isOpen, onClose, onConfirm, title, children }) => {
    if (!isOpen) return null;

    return (
        <div className="modal-backdrop">
            <div className="modal-content">
                <div className="modal-header">
                    <h5 className="modal-title">{title}</h5>
                    <button type="button" className="btn-close" onClick={onClose}></button>
                </div>
                <div className="modal-body">
                    {children}
                </div>
                <div className="modal-footer">
                    <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
                    <button type="button" className="btn btn-primary" onClick={onConfirm}>Confirmar</button>
                </div>
            </div>
        </div>
    );
};


// Componente principal da página
const ADExplorerPage = () => {
    const [treeData, setTreeData] = useState([]);
    const [selectedNode, setSelectedNode] = useState(null);
    const [members, setMembers] = useState([]);
    const [isMoveModalOpen, setIsMoveModalOpen] = useState(false); // Renomeado
    const [moveDetails, setMoveDetails] = useState(null);
    const [confirmationAction, setConfirmationAction] = useState({ isOpen: false }); // Novo estado
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [isSearchLoading, setIsSearchLoading] = useState(false);
    const [searchPerformed, setSearchPerformed] = useState(false);
    const [contextMenu, setContextMenu] = useState({ show: false, x: 0, y: 0, targetNode: null });
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [userPermissions, setUserPermissions] = useState({});
    const [isDisableTempModalOpen, setIsDisableTempModalOpen] = useState(false);
    const [isScheduleAbsenceModalOpen, setIsScheduleAbsenceModalOpen] = useState(false);
    const [actionUser, setActionUser] = useState(null); // Usuário para modais de ação

    useEffect(() => {
        axios.get('/api/action_permissions')
            .then(response => setUserPermissions(response.data))
            .catch(error => console.error("Erro ao buscar permissões:", error));
    }, []);

    // Handlers para as ações do menu de contexto
    const handleEdit = (node) => {
        if (node.type === 'user' && node.sam) {
            setEditingUser(node.sam);
            setIsEditModalOpen(true);
        }
    };

    const handleToggleStatus = (node) => {
        const actionText = node.status === 'Ativo' ? 'Desativar' : 'Ativar';
        setConfirmationAction({
            isOpen: true,
            title: `${actionText} Conta`,
            message: `Tem certeza que deseja ${actionText.toLowerCase()} a conta de ${node.name}?`,
            onConfirm: () => {
                axios.post('/api/toggle_object_status', { dn: node.dn, sam: node.sam })
                    .then(response => {
                        // TODO: Atualizar o estado local do nó para refletir a mudança
                        alert(response.data.message);
                    })
                    .catch(error => alert(error.response?.data?.error || 'Erro desconhecido'))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleResetPassword = (node) => {
        setConfirmationAction({
            isOpen: true,
            title: 'Resetar Senha',
            message: `Tem certeza que deseja resetar a senha de ${node.name}? Uma nova senha padrão será definida.`,
            onConfirm: () => {
                axios.post(`/api/reset_password/${node.sam}`)
                    .then(response => {
                        alert(`${response.data.message} Nova senha: ${response.data.new_password}`);
                    })
                    .catch(error => alert(error.response?.data?.error || 'Erro desconhecido'))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleDelete = (node) => {
        setConfirmationAction({
            isOpen: true,
            title: 'Excluir Objeto',
            message: `Atenção! Tem certeza que deseja excluir permanentemente ${node.name}? Esta ação não pode ser desfeita.`,
            onConfirm: () => {
                axios.delete('/api/delete_object', { data: { dn: node.dn, name: node.name } })
                    .then(response => {
                        // TODO: Remover o nó da UI
                        alert(response.data.message);
                    })
                    .catch(error => alert(error.response?.data?.error || 'Erro desconhecido'))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleDisableTemp = (node) => {
        if (node.type === 'user' && node.sam) {
            setActionUser(node.sam);
            setIsDisableTempModalOpen(true);
        }
    };

    const handleScheduleAbsence = (node) => {
        if (node.type === 'user' && node.sam) {
            setActionUser(node.sam);
            setIsScheduleAbsenceModalOpen(true);
        }
    };

    const handleContextMenu = (e, node) => {
        e.preventDefault();
        setContextMenu({
            show: true,
            x: e.clientX,
            y: e.clientY,
            targetNode: node
        });
    };

    // Função para simular o clique em um nó da árvore (para o duplo clique)
    const handleOuDoubleClick = (ouMember) => {
        // Encontra o nó correspondente nos dados da árvore para obter o estado completo
        // Esta é uma busca simples, pode ser otimizada se a árvore for muito grande
        let targetNode = null;
        const findNodeRecursive = (nodes, dn) => {
            for (const node of nodes) {
                if (node.dn === dn) {
                    targetNode = node;
                    return;
                }
                if (node.nodes) {
                    findNodeRecursive(node.nodes, dn);
                }
                if (targetNode) return;
            }
        };
        findNodeRecursive(treeData, ouMember.dn);

        if (targetNode) {
            handleNodeClick(targetNode, true);
        }
    };

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
                console.log("Dados recebidos da API:", response.data); // Log de Depuração
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
        if (sourceOuDn === targetNode.dn) return;

        setMoveDetails({ item, targetNode, sourceOuDn });
        setIsMoveModalOpen(true);
    }, []);

    const confirmMove = () => {
        if (!moveDetails) return;
        const { item, targetNode, sourceOuDn } = moveDetails;

        axios.post('/api/move_object', {
            object_dn: item.dn,
            target_ou_dn: targetNode.dn,
        })
        .then(response => {
            if (response.data.success) {
                if (selectedNode && selectedNode.dn === sourceOuDn) {
                    setMembers(prevMembers => prevMembers.filter(m => m.dn !== item.dn));
                }
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
        })
        .finally(() => {
            setIsMoveModalOpen(false);
            setMoveDetails(null);
        });
    };

    const handleSearchSubmit = (e) => {
        e.preventDefault();
        if (searchQuery.trim().length < 3) {
            alert('A busca deve ter no mínimo 3 caracteres.');
            return;
        }
        setIsSearchLoading(true);
        setSearchPerformed(true);
        setSelectedNode(null); // Limpa a seleção da OU para focar nos resultados da busca
        setMembers([]); // Limpa os membros da OU anterior
        axios.get(`/api/search_ad?q=${encodeURIComponent(searchQuery)}`)
            .then(response => {
                setSearchResults(response.data);
            })
            .catch(error => {
                console.error("Erro na busca:", error);
                const errorMessage = error.response?.data?.error || 'Ocorreu um erro ao realizar a busca.';
                alert(errorMessage);
                setSearchResults([]);
            })
            .finally(() => {
                setIsSearchLoading(false);
            });
    };

    const clearSearch = () => {
        setSearchQuery('');
        setSearchResults([]);
        setSearchPerformed(false);
        setSelectedNode(null);
        setMembers([]);
    };

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
            case 'computer': return <i className="fas fa-desktop"></i>;
            default: return <i className="fas fa-file"></i>;
        }
    };

    return (
        <DndProvider backend={HTML5Backend}>
            <div className="ad-explorer-container">
                <div className="panels-container">
                    <div className="tree-panel">
                        <div className="search-container">
                            <form onSubmit={handleSearchSubmit} className="search-form">
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Buscar usuário ou computador..."
                                    className="search-input"
                                />
                                <button type="submit" className="search-button" disabled={isSearchLoading}>
                                    {isSearchLoading ? <i className="fas fa-spinner fa-spin"></i> : <i className="fas fa-search"></i>}
                                </button>
                                {searchPerformed && (
                                    <button type="button" onClick={clearSearch} className="clear-button">
                                        <i className="fas fa-times"></i>
                                    </button>
                                )}
                            </form>
                        </div>
                        {treeData.map(rootNode => (
                            <TreeNode key={rootNode.dn} node={rootNode} onNodeClick={handleNodeClick} onMoveObject={handleMoveObject} onContextMenu={handleContextMenu} />
                        ))}
                    </div>
                    <ContentPanel
                        selectedNode={selectedNode}
                        members={searchPerformed ? searchResults : members}
                        getIcon={getIcon}
                        onOuDoubleClick={handleOuDoubleClick}
                        isSearchMode={searchPerformed}
                        onContextMenu={handleContextMenu}
                    />
                </div>
                {/* Modal de confirmação para a ação de MOVER */}
                <ConfirmationModal
                    isOpen={isMoveModalOpen}
                    onClose={() => setIsMoveModalOpen(false)}
                    onConfirm={confirmMove}
                    title="Confirmar Movimentação"
                >
                    {moveDetails && (
                        <p>
                            Tem certeza que deseja mover <strong>{moveDetails.item.name}</strong> para a Unidade Organizacional <strong>{moveDetails.targetNode.text}</strong>?
                        </p>
                    )}
                </ConfirmationModal>

                {/* Modal de confirmação GENÉRICO para outras ações */}
                <ConfirmationModal
                    isOpen={confirmationAction.isOpen}
                    onClose={() => setConfirmationAction({ isOpen: false })}
                    onConfirm={confirmationAction.onConfirm}
                    title={confirmationAction.title}
                >
                    <p>{confirmationAction.message}</p>
                </ConfirmationModal>

                <ContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    show={contextMenu.show}
                    targetNode={contextMenu.targetNode}
                    onClose={() => setContextMenu({ ...contextMenu, show: false })}
                    permissions={userPermissions}
                    onEdit={handleEdit}
                    onToggleStatus={handleToggleStatus}
                    onResetPassword={handleResetPassword}
                    onDelete={handleDelete}
                    onDisableTemp={handleDisableTemp}
                    onScheduleAbsence={handleScheduleAbsence}
                />
                <EditUserModal
                    isOpen={isEditModalOpen}
                    onClose={() => setIsEditModalOpen(false)}
                    username={editingUser}
                />
                <DisableTempModal
                    isOpen={isDisableTempModalOpen}
                    onClose={() => setIsDisableTempModalOpen(false)}
                    username={actionUser}
                />
                <ScheduleAbsenceModal
                    isOpen={isScheduleAbsenceModalOpen}
                    onClose={() => setIsScheduleAbsenceModalOpen(false)}
                    username={actionUser}
                />
            </div>
        </DndProvider>
    );
};

export default ADExplorerPage;
